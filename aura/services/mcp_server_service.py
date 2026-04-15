from __future__ import annotations

import json
from uuid import uuid4

from fastapi import HTTPException, status
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.domain.contracts import (
    AgentRunRequest,
    ChatRequest,
    McpServerCapabilities,
    McpToolDefinition,
    RequestContext,
    RetrievalRequest,
)
from aura.services.agent_service import AgentService
from aura.services.chat import ChatService
from aura.services.registry_service import RegistryService
from aura.services.retrieval import RetrievalService
from aura.services.space_service import SpaceService


class McpServerService:
    def __init__(
        self,
        *,
        retrieval_service: RetrievalService,
        chat_service: ChatService,
        agent_service: AgentService,
        space_service: SpaceService,
        registry_service: RegistryService,
    ) -> None:
        self._retrieval = retrieval_service
        self._chat = chat_service
        self._agents = agent_service
        self._spaces = space_service
        self._registry = registry_service
        self._redis = redis_from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

    async def open_session(self, context: RequestContext) -> str:
        session_id = uuid4().hex
        payload = {
            "tenant_id": str(context.tenant_id),
            "user_id": str(context.identity.user_id),
            "okta_sub": context.identity.okta_sub,
        }
        await self._redis.setex(self._session_key(session_id), 300, json.dumps(payload))
        return session_id

    async def stream(self, session_id: str):
        yield self._sse_event("endpoint", f"/mcp/v1/sse/messages/{session_id}")
        while await self._redis.exists(self._session_key(session_id)):
            item = await self._redis.blpop(self._queue_key(session_id), timeout=1)
            if item is None:
                yield ": keep-alive\n\n"
                continue
            _, payload = item
            yield self._sse_event("message", payload)

    async def close_session(self, session_id: str) -> None:
        await self._redis.delete(self._session_key(session_id), self._queue_key(session_id))

    async def handle_message(
        self,
        *,
        session_id: str,
        session: AsyncSession,
        context: RequestContext,
        payload: dict,
    ) -> dict | None:
        session_payload = await self._redis.get(self._session_key(session_id))
        if session_payload is None:
            raise ValueError("MCP session not found.")
        self._ensure_session_owner(session_payload=session_payload, context=context)
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "notifications/initialized" and request_id is None:
            return None
        response: dict
        try:
            response = await self._dispatch(session=session, context=context, payload=payload)
        except HTTPException:
            raise
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": "internal_error", "message": str(exc)},
            }
        if request_id is not None:
            await self._redis.rpush(self._queue_key(session_id), json.dumps(response))
            await self._redis.expire(self._queue_key(session_id), 300)
        return response if request_id is not None else None

    async def _dispatch(self, *, session: AsyncSession, context: RequestContext, payload: dict) -> dict:
        request_id = payload.get("id")
        method = payload.get("method")
        params = dict(payload.get("params") or {})
        if method == "initialize":
            capabilities = McpServerCapabilities(
                tools=[tool.name for tool in self._tool_definitions()],
                tenant_id=context.tenant_id,
                identity_sub=context.identity.okta_sub,
                server_version="0.1.0",
            )
            result = {
                "protocolVersion": params.get("protocolVersion", "2025-03-26"),
                "serverInfo": {"name": "aura", "version": "0.1.0"},
                "capabilities": {"tools": {}},
                "auraCapabilities": capabilities.model_dump(mode="json"),
            }
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        if method == "tools/list":
            tools = [tool.model_dump() for tool in self._tool_definitions()]
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
        if method != "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": "method_not_found", "message": f"Unsupported method: {method}"},
            }

        tool_name = params.get("name")
        arguments = dict(params.get("arguments") or {})
        result = await self._call_tool(
            session=session,
            context=context,
            tool_name=str(tool_name),
            arguments=arguments,
        )
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    async def _call_tool(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        if tool_name == "aura_list_spaces":
            spaces = await self._spaces.list_spaces(session, context.identity)
            return {"content": [{"type": "text", "text": json.dumps([space.model_dump(mode="json") for space in spaces])}]}
        if tool_name == "aura_list_agents":
            versions = await self._registry.list_versions(session, context.tenant_id)
            published = [version for version in versions if version.status == "published"]
            data = [{"name": version.name, "version": version.version} for version in published]
            return {"content": [{"type": "text", "text": json.dumps(data)}]}
        if tool_name == "aura_retrieve":
            retrieval_result = await self._retrieval.retrieve(
                session=session,
                request=RetrievalRequest.model_validate(arguments),
                context=context,
            )
            return {"content": [{"type": "text", "text": retrieval_result.model_dump_json()}]}
        if tool_name == "aura_chat":
            chat_result = await self._chat.respond(
                session=session,
                request=ChatRequest.model_validate(arguments),
                context=context,
            )
            return {"content": [{"type": "text", "text": chat_result.model_dump_json()}]}
        if tool_name == "aura_agent_run":
            agent_result = await self._agents.run_agent(
                session=session,
                request=AgentRunRequest.model_validate(arguments),
                context=context,
            )
            return {"content": [{"type": "text", "text": agent_result.model_dump_json()}]}
        return {
            "content": [{"type": "text", "text": json.dumps({"error": {"code": "tool_not_found", "message": tool_name}})}],
            "isError": True,
            "error_message": f"Unknown tool: {tool_name}",
        }

    def _tool_definitions(self) -> list[McpToolDefinition]:
        return [
            McpToolDefinition(name="aura_retrieve", description="Hybrid retrieval across allowed spaces.", input_schema={"type": "object"}),
            McpToolDefinition(name="aura_chat", description="Non-streaming chat response.", input_schema={"type": "object"}),
            McpToolDefinition(name="aura_agent_run", description="Run a published AURA agent.", input_schema={"type": "object"}),
            McpToolDefinition(name="aura_list_spaces", description="List spaces visible to the current identity.", input_schema={"type": "object"}),
            McpToolDefinition(name="aura_list_agents", description="List published agents for the current tenant.", input_schema={"type": "object"}),
        ]

    def _queue_key(self, session_id: str) -> str:
        return f"aura:mcp:queue:{session_id}"

    def _session_key(self, session_id: str) -> str:
        return f"aura:mcp:session:{session_id}"

    def _sse_event(self, event: str, data: str) -> str:
        return f"event: {event}\ndata: {data}\n\n"

    def _ensure_session_owner(self, *, session_payload: str, context: RequestContext) -> None:
        owner = json.loads(session_payload)
        if owner.get("tenant_id") != str(context.tenant_id) or owner.get("okta_sub") != context.identity.okta_sub:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MCP session does not belong to this identity.")
