from __future__ import annotations

import pytest

from aura.domain.contracts import CredentialType, McpToolDefinition, McpToolResult, ResolvedCredentials
from aura.services.skill_service import _FilteredMcpBridgeAdapter


class _FakeMcpAdapter:
    async def list_tools(self) -> list[McpToolDefinition]:
        return [
            McpToolDefinition(name="allowed_tool", description="allowed", input_schema={}),
            McpToolDefinition(name="blocked_tool", description="blocked", input_schema={}),
        ]

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        credentials: ResolvedCredentials,
        timeout: int,
    ) -> McpToolResult:
        return McpToolResult(
            tool_name=tool_name,
            content=[{"type": "text", "text": f"{tool_name}:{arguments['value']}:{credentials.credential_type}:{timeout}"}],
        )


@pytest.mark.asyncio
async def test_filtered_mcp_adapter_only_exposes_whitelisted_tools() -> None:
    adapter = _FilteredMcpBridgeAdapter(delegate=_FakeMcpAdapter(), allowed_tools={"allowed_tool"})

    tools = await adapter.list_tools()

    assert [tool.name for tool in tools] == ["allowed_tool"]


@pytest.mark.asyncio
async def test_filtered_mcp_adapter_blocks_tool_calls_outside_whitelist() -> None:
    adapter = _FilteredMcpBridgeAdapter(delegate=_FakeMcpAdapter(), allowed_tools={"allowed_tool"})
    credentials = ResolvedCredentials(credential_type=CredentialType.oauth2_bearer, token_or_key="secret")

    blocked = await adapter.call_tool("blocked_tool", {"value": "x"}, credentials, 5)
    allowed = await adapter.call_tool("allowed_tool", {"value": "x"}, credentials, 5)

    assert blocked.is_error is True
    assert blocked.error_message == "MCP tool 'blocked_tool' is not exposed for this skill."
    assert allowed.is_error is False
    assert allowed.content == [{"type": "text", "text": "allowed_tool:x:CredentialType.oauth2_bearer:5"}]
