from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import SandboxPolicy as SandboxPolicyModel
from aura.adapters.db.models import SkillPackage, SkillVersion
from aura.adapters.mcp import HttpSseMcpBridgeAdapter, McpBridgeAdapter
from aura.adapters.registry.skill_manifest_validator import SkillManifestValidationError, SkillManifestValidator
from aura.adapters.s3.client import S3Client
from aura.adapters.sandbox.provider import SandboxProvider
from aura.domain.contracts import ConnectorCredentials, McpToolDefinition, McpToolResult, RequestContext, SandboxInput, SandboxResult
from aura.services.policy_service import PolicyService
from aura.utils.observability import record_sandbox_wall_time
from aura.utils.secrets import EnvSecretStore, SecretStore, resolve_credentials


@dataclass(slots=True)
class ResolvedSkillVersion:
    id: UUID
    tenant_id: UUID
    name: str
    version: str
    status: str
    entrypoint: str
    artifact_ref: str
    artifact_sha256: str
    manifest: dict
    sandbox_policy_id: UUID | None
    timeout_s: int
    created_by: UUID
    created_at: datetime

    @property
    def skill_type(self) -> str:
        return str(self.manifest.get("skill_type") or "sandbox_python")

    @property
    def exposed_tools(self) -> list[str]:
        return list(self.manifest.get("exposed_tools") or [])


class SkillExecutionError(RuntimeError):
    def __init__(self, *, status: str, error_message: str | None, exit_code: int | None, artifacts: list[dict], wall_time_s: float) -> None:
        super().__init__(error_message or "Skill execution failed.")
        self.status = status
        self.error_message = error_message
        self.exit_code = exit_code
        self.artifacts = artifacts
        self.wall_time_s = wall_time_s


@dataclass(slots=True)
class SkillRunDetails:
    status: str
    output: dict[str, Any]
    artifacts: list[dict[str, Any]]
    error_message: str | None
    exit_code: int | None
    wall_time_s: float


class _FilteredMcpBridgeAdapter:
    def __init__(self, *, delegate: McpBridgeAdapter, allowed_tools: set[str]) -> None:
        self._delegate = delegate
        self._allowed_tools = allowed_tools

    async def list_tools(self) -> list[McpToolDefinition]:
        tools = await self._delegate.list_tools()
        return [tool for tool in tools if tool.name in self._allowed_tools]

    async def call_tool(self, tool_name: str, arguments: dict, credentials: Any, timeout: int) -> McpToolResult:
        if tool_name not in self._allowed_tools:
            return McpToolResult(
                tool_name=tool_name,
                content=[],
                is_error=True,
                error_message=f"MCP tool '{tool_name}' is not exposed for this skill.",
            )
        return await self._delegate.call_tool(tool_name, arguments, credentials, timeout)

    async def aclose(self) -> None:
        close = getattr(self._delegate, "aclose", None)
        if callable(close):
            await close()


class SkillService:
    def __init__(
        self,
        *,
        validator: SkillManifestValidator | None = None,
        s3_client: S3Client | None = None,
        sandbox_provider: SandboxProvider | None = None,
        policy_service: PolicyService | None = None,
        secret_store: SecretStore | None = None,
        mcp_adapter_factory: Any | None = None,
    ) -> None:
        self._validator = validator or SkillManifestValidator()
        self._s3 = s3_client or S3Client()
        self._sandbox = sandbox_provider
        self._policies = policy_service or PolicyService()
        self._secret_store = secret_store or EnvSecretStore()
        self._mcp_adapter_factory = mcp_adapter_factory or (lambda url: HttpSseMcpBridgeAdapter(server_url=url))

    async def upload_and_validate(
        self,
        *,
        session: AsyncSession,
        zip_bytes: bytes | None,
        manifest_yaml: str,
        uploaded_by: UUID,
        tenant_id: UUID,
    ) -> SkillVersion:
        try:
            validated = self._validator.validate(manifest_yaml, zip_bytes=zip_bytes)
        except SkillManifestValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors) from exc
        manifest = validated.data
        raw_artifact = zip_bytes or b""
        artifact_sha256 = hashlib.sha256(raw_artifact).hexdigest()
        artifact_key = f"skills/{tenant_id}/{manifest['name']}/{manifest['version']}/{artifact_sha256}.zip"
        artifact_ref = (
            await self._s3.upload_file(settings.s3_bucket_name, artifact_key, raw_artifact, "application/zip")
            if raw_artifact
            else f"inline://{manifest['name']}/{manifest['version']}"
        )
        package = await session.scalar(
            select(SkillPackage).where(SkillPackage.tenant_id == tenant_id, SkillPackage.name == manifest["name"])
        )
        if package is None:
            package = SkillPackage(tenant_id=tenant_id, name=manifest["name"])
            session.add(package)
            await session.flush()

        sandbox_policy_id = await self._resolve_policy_id(
            session,
            tenant_id,
            manifest.get("sandbox_policy"),
        )
        persisted_status = "validated" if validated.smoke_test_passed and manifest["status"] != "draft" else "draft"
        version = SkillVersion(
            skill_package_id=package.id,
            tenant_id=tenant_id,
            version=manifest["version"],
            entrypoint=manifest["entrypoint"],
            manifest=manifest,
            artifact_ref=artifact_ref,
            artifact_sha256=artifact_sha256,
            status=persisted_status,
            sandbox_policy_id=sandbox_policy_id,
            timeout_s=int(manifest.get("timeout") or manifest.get("timeout_s") or 120),
            created_by=uploaded_by,
        )
        session.add(version)
        await session.flush()
        return version

    async def publish(self, session: AsyncSession, skill_version_id: UUID) -> SkillVersion:
        version = await session.scalar(select(SkillVersion).where(SkillVersion.id == skill_version_id))
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill version not found.")
        if version.status != "validated":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only validated skills can be published.")
        version.status = "published"
        await session.flush()
        return version

    async def list_versions(self, session: AsyncSession, tenant_id: UUID) -> list[ResolvedSkillVersion]:
        rows = (
            await session.execute(
                select(SkillVersion, SkillPackage.name)
                .join(SkillPackage, SkillPackage.id == SkillVersion.skill_package_id)
                .where(SkillPackage.tenant_id == tenant_id)
                .order_by(SkillPackage.name, desc(SkillVersion.created_at))
            )
        ).all()
        return [self._to_resolved(version, name) for version, name in rows]

    async def run_skill(
        self,
        *,
        session: AsyncSession,
        skill_name: str,
        input_obj: dict,
        context: RequestContext,
    ) -> dict[str, Any]:
        result = await self.execute_skill(session=session, skill_name=skill_name, input_obj=input_obj, context=context)
        if result.status != "succeeded":
            raise SkillExecutionError(
                status=result.status,
                error_message=result.error_message,
                exit_code=result.exit_code,
                artifacts=[artifact.model_dump() for artifact in result.artifacts],
                wall_time_s=result.wall_time_s,
            )
        return result.output or {}

    async def run_skill_detailed(
        self,
        *,
        session: AsyncSession,
        skill_name: str,
        input_obj: dict,
        context: RequestContext,
    ) -> SkillRunDetails:
        result = await self.execute_skill(session=session, skill_name=skill_name, input_obj=input_obj, context=context)
        return SkillRunDetails(
            status=result.status,
            output=result.output or {},
            artifacts=[artifact.model_dump() for artifact in result.artifacts],
            error_message=result.error_message,
            exit_code=result.exit_code,
            wall_time_s=result.wall_time_s,
        )

    async def execute_skill(
        self,
        *,
        session: AsyncSession,
        skill_name: str,
        input_obj: dict,
        context: RequestContext,
    ) -> SandboxResult:
        version = await self.resolve_skill_version(session=session, skill_name=skill_name, tenant_id=context.tenant_id)
        if version.status != "published":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only published skills are executable.")
        if version.skill_type == "mcp_client":
            return await self._execute_mcp_skill(version=version, input_obj=input_obj)

        if self._sandbox is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox provider is not configured.")
        policy = await self._policies.resolve_sandbox_policy(session, version, context)
        sandbox_input = SandboxInput(
            skill_version_id=version.id,
            artifact_ref=version.artifact_ref,
            entrypoint=version.entrypoint,
            input_obj=input_obj,
            profile=policy,
            trace_id=context.trace_id,
        )
        result = await self._sandbox.run(sandbox_input)
        record_sandbox_wall_time(skill_name=skill_name, status=result.status, wall_time_s=result.wall_time_s)
        return result

    async def resolve_skill_version(
        self,
        *,
        session: AsyncSession,
        skill_name: str,
        tenant_id: UUID,
    ) -> ResolvedSkillVersion:
        row = (
            await session.execute(
                select(SkillVersion, SkillPackage.name)
                .join(SkillPackage, SkillPackage.id == SkillVersion.skill_package_id)
                .where(
                    SkillPackage.tenant_id == tenant_id,
                    SkillPackage.name == skill_name,
                )
                .order_by(
                    (SkillVersion.status == "published").desc(),
                    desc(SkillVersion.created_at),
                )
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found.")
        version, name = row
        return self._to_resolved(version, name)

    async def resolve_mcp_adapters(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        allowed_tools: list[str],
    ) -> dict[str, McpBridgeAdapter]:
        adapters: dict[str, McpBridgeAdapter] = {}
        allowed_mcp_tools_by_skill: dict[str, set[str]] = {}
        for tool in allowed_tools:
            parts = tool.split(".", 2)
            if len(parts) == 3 and parts[0] == "mcp":
                allowed_mcp_tools_by_skill.setdefault(parts[1], set()).add(parts[2])
        for skill_name, allowed_tool_names in allowed_mcp_tools_by_skill.items():
            version = await self.resolve_skill_version(session=session, skill_name=skill_name, tenant_id=tenant_id)
            if version.status != "published" or version.skill_type != "mcp_client":
                continue
            exposed_tools = set(version.exposed_tools)
            effective_tools = exposed_tools & allowed_tool_names
            if not effective_tools:
                continue
            adapters[skill_name] = _FilteredMcpBridgeAdapter(
                delegate=self._mcp_adapter_factory(version.manifest["mcp_server_url"]),
                allowed_tools=effective_tools,
            )
        return adapters

    async def _execute_mcp_skill(self, *, version: ResolvedSkillVersion, input_obj: dict) -> SandboxResult:
        tool_name = str(input_obj.get("tool_name") or "")
        arguments = dict(input_obj.get("arguments") or {})
        if tool_name not in version.exposed_tools:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requested MCP tool is not exposed.")
        credentials = await resolve_credentials(
            ConnectorCredentials.model_validate(version.manifest["mcp_auth"]),
            self._secret_store,
        )
        adapter = _FilteredMcpBridgeAdapter(
            delegate=self._mcp_adapter_factory(version.manifest["mcp_server_url"]),
            allowed_tools=set(version.exposed_tools),
        )
        started_at = time.monotonic()
        try:
            result: McpToolResult = await adapter.call_tool(tool_name, arguments, credentials, version.timeout_s)
            return SandboxResult(
                status="failed" if result.is_error else "succeeded",
                output=result.model_dump() if not result.is_error else None,
                artifacts=[],
                error_message=result.error_message,
                exit_code=None,
                wall_time_s=time.monotonic() - started_at,
            )
        finally:
            await adapter.aclose()

    async def _resolve_policy_id(self, session: AsyncSession, tenant_id: UUID, policy_name: str | None) -> UUID | None:
        if not policy_name:
            return None
        return await session.scalar(
            select(SandboxPolicyModel.id).where(
                SandboxPolicyModel.tenant_id == tenant_id,
                SandboxPolicyModel.name == policy_name,
            )
        )

    def _to_resolved(self, version: SkillVersion, name: str) -> ResolvedSkillVersion:
        return ResolvedSkillVersion(
            id=version.id,
            tenant_id=version.tenant_id,
            name=name,
            version=version.version,
            status=version.status,
            entrypoint=version.entrypoint,
            artifact_ref=version.artifact_ref,
            artifact_sha256=version.artifact_sha256,
            manifest=version.manifest,
            sandbox_policy_id=version.sandbox_policy_id,
            timeout_s=version.timeout_s,
            created_by=version.created_by,
            created_at=version.created_at,
        )
