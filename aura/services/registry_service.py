from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import AgentPackage, AgentTriggerRegistration, AgentVersion, PiiPolicy, ModelPolicy, SandboxPolicy
from aura.adapters.registry.manifest_validator import ManifestValidator
from aura.adapters.s3.client import S3Client
from aura.domain.contracts import CronTrigger

if TYPE_CHECKING:
    class _TriggerScheduler(Protocol):
        async def register_cron(
            self,
            session: AsyncSession,
            agent_version_id: UUID,
            trigger: CronTrigger,
            tenant_id: UUID,
        ) -> None: ...


@dataclass(slots=True)
class ResolvedAgentVersion:
    id: UUID
    tenant_id: UUID
    name: str
    version: str
    status: str
    entrypoint: str
    artifact_ref: str
    artifact_sha256: str
    agent_type: str
    timeout_s: int
    manifest: dict
    model_policy_id: UUID | None
    pii_policy_id: UUID | None
    sandbox_policy_id: UUID | None
    max_budget_usd: Decimal | None
    published_at: datetime | None
    created_by: UUID
    created_at: datetime

    @property
    def allowed_tools(self) -> list[str]:
        return list(self.manifest.get("allowed_tools") or [])

    @property
    def allowed_space_ids(self) -> list[UUID]:
        return [UUID(str(item)) for item in (self.manifest.get("allowed_spaces") or [])]

    @property
    def triggers(self) -> list[dict]:
        return list(self.manifest.get("triggers") or [])


class RegistryService:
    def __init__(
        self,
        *,
        manifest_validator: ManifestValidator | None = None,
        s3_client: S3Client | None = None,
    ) -> None:
        self._validator = manifest_validator or ManifestValidator()
        self._s3 = s3_client or S3Client()

    async def upload_and_validate(
        self,
        session: AsyncSession,
        zip_bytes: bytes,
        manifest_yaml: str,
        uploaded_by: UUID,
        tenant_id: UUID,
    ) -> AgentVersion:
        validated = self._validator.validate(manifest_yaml, zip_bytes=zip_bytes)
        manifest = validated.data
        artifact_sha256 = hashlib.sha256(zip_bytes).hexdigest()
        artifact_key = f"agents/{tenant_id}/{manifest['name']}/{manifest['version']}/{artifact_sha256}.zip"
        artifact_ref = await self._s3.upload_file(
            settings.s3_bucket_name,
            artifact_key,
            zip_bytes,
            "application/zip",
        )
        package = await session.scalar(
            select(AgentPackage).where(AgentPackage.tenant_id == tenant_id, AgentPackage.name == manifest["name"])
        )
        if package is None:
            package = AgentPackage(tenant_id=tenant_id, name=manifest["name"])
            session.add(package)
            await session.flush()

        model_policy_id = await self._resolve_policy_id(session, ModelPolicy, tenant_id, manifest.get("model_policy"))
        pii_policy_id = await self._resolve_policy_id(session, PiiPolicy, tenant_id, manifest.get("pii_policy"))
        sandbox_policy_id = await self._resolve_policy_id(session, SandboxPolicy, tenant_id, manifest.get("sandbox_policy"))

        persisted_status = "validated" if validated.smoke_test_passed and manifest["status"] != "draft" else "draft"
        version = AgentVersion(
            agent_package_id=package.id,
            tenant_id=tenant_id,
            version=manifest["version"],
            agent_type=manifest["agent_type"],
            entrypoint=manifest["entrypoint"],
            manifest=manifest,
            artifact_ref=artifact_ref,
            artifact_sha256=artifact_sha256,
            status=persisted_status,
            model_policy_id=model_policy_id,
            pii_policy_id=pii_policy_id,
            sandbox_policy_id=sandbox_policy_id,
            max_budget_usd=manifest.get("max_budget_usd"),
            timeout_s=manifest["timeout_s"],
            created_by=uploaded_by,
        )
        session.add(version)
        await session.flush()
        return version

    async def publish(
        self,
        session: AsyncSession,
        agent_version_id: UUID,
        *,
        tenant_id: UUID | None = None,
        trigger_scheduler: "_TriggerScheduler | None" = None,
    ) -> AgentVersion:
        version = await session.scalar(select(AgentVersion).where(AgentVersion.id == agent_version_id))
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent version not found.")
        if version.status != "validated":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only validated versions can be published.")
        version.status = "published"
        version.published_at = datetime.now(UTC)
        await session.flush()
        effective_tenant_id = tenant_id or version.tenant_id
        await self._register_triggers(session, version, effective_tenant_id, trigger_scheduler)
        return version

    async def _register_triggers(
        self,
        session: AsyncSession,
        version: AgentVersion,
        tenant_id: UUID,
        trigger_scheduler: "_TriggerScheduler | None",
    ) -> None:
        for trigger in list(version.manifest.get("triggers") or []):
            trigger_type = trigger.get("type")
            if trigger_type == "cron" and trigger_scheduler is not None:
                from aura.domain.contracts import CronTrigger as _CronTrigger  # noqa: PLC0415
                await trigger_scheduler.register_cron(
                    session=session,
                    agent_version_id=version.id,
                    trigger=_CronTrigger.model_validate(trigger),
                    tenant_id=tenant_id,
                )
            elif trigger_type == "event":
                session.add(
                    AgentTriggerRegistration(
                        tenant_id=tenant_id,
                        agent_version_id=version.id,
                        trigger_type="event",
                        trigger_config=trigger,
                        status="active",
                    )
                )
        await session.flush()

    async def resolve_agent_version(
        self,
        session: AsyncSession,
        agent_name: str,
        requested_version: str | None,
        tenant_id: UUID,
    ) -> ResolvedAgentVersion:
        if requested_version is not None:
            statement = (
                select(AgentVersion, AgentPackage.name)
                .join(AgentPackage, AgentPackage.id == AgentVersion.agent_package_id)
                .where(
                    AgentPackage.tenant_id == tenant_id,
                    AgentPackage.name == agent_name,
                    AgentVersion.version == requested_version,
                )
            )
            row = (await session.execute(statement)).first()
        else:
            published_statement = (
                select(AgentVersion, AgentPackage.name)
                .join(AgentPackage, AgentPackage.id == AgentVersion.agent_package_id)
                .where(
                    AgentPackage.tenant_id == tenant_id,
                    AgentPackage.name == agent_name,
                    AgentVersion.status == "published",
                )
                .order_by(desc(AgentVersion.published_at), desc(AgentVersion.created_at))
            )
            row = (await session.execute(published_statement)).first()
            if row is None:
                latest_statement = (
                    select(AgentVersion, AgentPackage.name)
                    .join(AgentPackage, AgentPackage.id == AgentVersion.agent_package_id)
                    .where(AgentPackage.tenant_id == tenant_id, AgentPackage.name == agent_name)
                    .order_by(desc(AgentVersion.created_at))
                )
                row = (await session.execute(latest_statement)).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
        version, name = row
        return ResolvedAgentVersion(
            id=version.id,
            tenant_id=version.tenant_id,
            name=name,
            version=version.version,
            status=version.status,
            entrypoint=version.entrypoint,
            artifact_ref=version.artifact_ref,
            artifact_sha256=version.artifact_sha256,
            agent_type=version.agent_type,
            timeout_s=version.timeout_s,
            manifest=version.manifest,
            model_policy_id=version.model_policy_id,
            pii_policy_id=version.pii_policy_id,
            sandbox_policy_id=version.sandbox_policy_id,
            max_budget_usd=version.max_budget_usd,
            published_at=version.published_at,
            created_by=version.created_by,
            created_at=version.created_at,
        )

    async def list_versions(self, session: AsyncSession, tenant_id: UUID) -> list[ResolvedAgentVersion]:
        rows = (
            await session.execute(
                select(AgentVersion, AgentPackage.name)
                .join(AgentPackage, AgentPackage.id == AgentVersion.agent_package_id)
                .where(AgentPackage.tenant_id == tenant_id)
                .order_by(AgentPackage.name, desc(AgentVersion.created_at))
            )
        ).all()
        return [
            ResolvedAgentVersion(
                id=version.id,
                tenant_id=version.tenant_id,
                name=name,
                version=version.version,
                status=version.status,
                entrypoint=version.entrypoint,
                artifact_ref=version.artifact_ref,
                artifact_sha256=version.artifact_sha256,
                agent_type=version.agent_type,
                timeout_s=version.timeout_s,
                manifest=version.manifest,
                model_policy_id=version.model_policy_id,
                pii_policy_id=version.pii_policy_id,
                sandbox_policy_id=version.sandbox_policy_id,
                max_budget_usd=version.max_budget_usd,
                published_at=version.published_at,
                created_by=version.created_by,
                created_at=version.created_at,
            )
            for version, name in rows
        ]

    async def _resolve_policy_id(self, session: AsyncSession, model, tenant_id: UUID, name: str | None) -> UUID | None:
        if not name:
            return None
        return await session.scalar(select(model.id).where(model.tenant_id == tenant_id, model.name == name))
