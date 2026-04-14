from __future__ import annotations

from aura.domain.contracts import SandboxInput, SandboxResult


class K8sJobSandboxProvider:
    async def run(self, sandbox_input: SandboxInput) -> SandboxResult:
        del sandbox_input
        raise NotImplementedError("K8s sandbox: implement for prod deployment")

    async def health_check(self) -> bool:
        return False
