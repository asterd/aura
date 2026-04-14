from __future__ import annotations

from typing import Protocol

from aura.domain.contracts import McpToolDefinition, McpToolResult, ResolvedCredentials


class McpBridgeAdapter(Protocol):
    async def list_tools(self) -> list[McpToolDefinition]: ...

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        credentials: ResolvedCredentials,
        timeout: int,
    ) -> McpToolResult: ...
