from __future__ import annotations

import asyncio
import json
from contextlib import AbstractAsyncContextManager
from typing import Any
from urllib.parse import urljoin

import httpx

from apps.api.config import settings
from aura.domain.contracts import McpToolDefinition, McpToolResult, ResolvedCredentials


class HttpSseMcpBridgeAdapter:
    def __init__(
        self,
        *,
        server_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._server_url = server_url
        self._client = client or httpx.AsyncClient(timeout=settings.mcp_client_timeout_s + 5)
        self._owns_client = client is None

    async def __aenter__(self) -> "HttpSseMcpBridgeAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        await self.aclose()

    async def list_tools(self) -> list[McpToolDefinition]:
        async with self._session() as session:
            response = await self._request(session, "tools/list", {})
        tools = response.get("tools") or []
        return [McpToolDefinition.model_validate(tool) for tool in tools]

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        credentials: ResolvedCredentials,
        timeout: int,
    ) -> McpToolResult:
        headers = self._build_auth_headers(credentials)
        async with self._session(headers=headers, timeout=timeout) as session:
            response = await self._request(
                session,
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
        return McpToolResult(
            tool_name=tool_name,
            content=list(response.get("content") or []),
            is_error=bool(response.get("isError") or response.get("is_error")),
            error_message=response.get("error_message"),
        )

    def _session(self, headers: dict[str, str] | None = None, timeout: int | None = None) -> "_McpClientSession":
        return _McpClientSession(
            http_client=self._client,
            sse_url=self._server_url,
            headers=headers or {},
            timeout=timeout or settings.mcp_client_timeout_s,
        )

    def _build_auth_headers(self, credentials: ResolvedCredentials) -> dict[str, str]:
        if credentials.credential_type == "basic":
            return {"Authorization": f"Basic {credentials.token_or_key}"}
        return {"Authorization": f"Bearer {credentials.token_or_key}"}

    async def _request(self, session: "_McpClientSession", method: str, params: dict[str, Any]) -> dict[str, Any]:
        initialize_result = await session.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "aura", "version": "0.1.0"},
            },
        )
        del initialize_result
        await session.notify("notifications/initialized", {})
        return await session.request(method, params)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class _McpClientSession:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        sse_url: str,
        headers: dict[str, str],
        timeout: int,
    ) -> None:
        self._http_client = http_client
        self._sse_url = sse_url
        self._headers = headers
        self._timeout = timeout
        self._stream_context: AbstractAsyncContextManager[httpx.Response] | None = None
        self._response: httpx.Response | None = None
        self._event_iter: Any = None
        self._message_url: str | None = None
        self._next_id = 0

    async def __aenter__(self) -> "_McpClientSession":
        bootstrap_headers = dict(self._headers)
        bootstrap_headers["x-aura-mcp-bootstrap"] = "1"
        bootstrap_response = await self._http_client.get(self._sse_url, headers=bootstrap_headers, timeout=self._timeout)
        if bootstrap_response.headers.get("content-type", "").startswith("application/json"):
            payload = bootstrap_response.json()
            message_endpoint = payload.get("message_endpoint")
            if message_endpoint:
                self._message_url = urljoin(str(bootstrap_response.url), message_endpoint)
                return self
        self._stream_context = self._http_client.stream("GET", self._sse_url, headers=self._headers, timeout=self._timeout)
        self._response = await self._stream_context.__aenter__()
        self._response.raise_for_status()
        message_endpoint = self._response.headers.get("x-mcp-message-endpoint")
        if message_endpoint:
            self._message_url = urljoin(str(self._response.url), message_endpoint)
            await self._stream_context.__aexit__(None, None, None)
            self._stream_context = None
            self._response = None
            return self
        self._event_iter = self._iter_sse_events()
        self._message_url = await self._read_message_url()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        if self._stream_context is not None:
            await self._stream_context.__aexit__(None, None, None)

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        response = await self._post_payload(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        if self._event_iter is None:
            payload = response.json()
            if payload.get("id") == request_id:
                if "error" in payload:
                    message = payload["error"].get("message", "MCP request failed.")
                    raise RuntimeError(message)
                return dict(payload.get("result") or {})
        if response.headers.get("content-type", "").startswith("application/json"):
            payload = response.json()
            if payload.get("id") == request_id:
                if "error" in payload:
                    message = payload["error"].get("message", "MCP request failed.")
                    raise RuntimeError(message)
                return dict(payload.get("result") or {})
        result = await self._wait_for_response(request_id)
        if "error" in result:
            message = result["error"].get("message", "MCP request failed.")
            raise RuntimeError(message)
        return dict(result.get("result") or {})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._post_payload({"jsonrpc": "2.0", "method": method, "params": params})

    async def _post_payload(self, payload: dict[str, Any]) -> httpx.Response:
        if self._message_url is None:
            raise RuntimeError("MCP session was not initialized.")
        return await self._http_client.post(
            self._message_url,
            json=payload,
            headers=self._headers,
            timeout=self._timeout,
        )

    async def _wait_for_response(self, request_id: int) -> dict[str, Any]:
        assert self._event_iter is not None
        deadline = asyncio.get_running_loop().time() + self._timeout
        async for event_name, data in self._event_iter:
            if event_name == "message":
                payload = json.loads(data)
                if payload.get("id") == request_id:
                    return payload
            if asyncio.get_running_loop().time() >= deadline:
                break
        raise TimeoutError(f"MCP response timed out for request {request_id}.")

    async def _read_message_url(self) -> str:
        assert self._event_iter is not None
        assert self._response is not None
        async for event_name, data in self._event_iter:
            if event_name == "endpoint":
                return urljoin(str(self._response.url), data)
        raise RuntimeError("MCP endpoint event not received.")

    async def _iter_sse_events(self):
        assert self._response is not None
        event_name = "message"
        data_lines: list[str] = []
        async for raw_line in self._response.aiter_lines():
            if raw_line == "":
                if data_lines:
                    yield event_name, "\n".join(data_lines)
                event_name = "message"
                data_lines = []
                continue
            if raw_line.startswith(":"):
                continue
            if raw_line.startswith("event:"):
                event_name = raw_line.removeprefix("event:").strip()
                continue
            if raw_line.startswith("data:"):
                data_lines.append(raw_line.removeprefix("data:").strip())
