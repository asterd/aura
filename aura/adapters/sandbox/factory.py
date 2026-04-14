from __future__ import annotations

from apps.api.config import settings
from aura.adapters.sandbox.docker import DockerSandboxProvider
from aura.adapters.sandbox.k8s import K8sJobSandboxProvider
from aura.adapters.sandbox.provider import SandboxProvider


def get_default() -> SandboxProvider:
    if settings.sandbox_provider == "docker":
        return DockerSandboxProvider()
    if settings.sandbox_provider == "k8s":
        return K8sJobSandboxProvider()
    raise ValueError(f"Unknown sandbox provider: {settings.sandbox_provider}")
