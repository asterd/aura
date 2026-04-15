from __future__ import annotations

import pytest

from aura.adapters.mcp.http_sse import HttpSseMcpBridgeAdapter


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_http_sse_adapter_closes_owned_client() -> None:
    adapter = HttpSseMcpBridgeAdapter(server_url="https://example.test/mcp")

    await adapter.aclose()

    assert adapter._client.is_closed is True  # noqa: SLF001


@pytest.mark.asyncio
async def test_http_sse_adapter_does_not_close_injected_client() -> None:
    client = _FakeAsyncClient()
    adapter = HttpSseMcpBridgeAdapter(server_url="https://example.test/mcp", client=client)

    await adapter.aclose()

    assert client.closed is False

