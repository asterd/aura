from __future__ import annotations

from typing import Protocol

from aura.domain.contracts import SandboxInput, SandboxResult


class SandboxProvider(Protocol):
    async def run(self, sandbox_input: SandboxInput) -> SandboxResult: ...

    async def health_check(self) -> bool: ...
