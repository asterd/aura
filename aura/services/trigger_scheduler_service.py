from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import AgentTriggerRegistration
from aura.domain.contracts import AgentRunRequest, CronTrigger, RequestContext, UserIdentity
from aura.services.agent_service import AgentService
from aura.services.registry_service import RegistryService


class TriggerSchedulerService:
    def __init__(
        self,
        *,
        agent_service: AgentService | None = None,
        registry_service: RegistryService | None = None,
    ) -> None:
        self._agents = agent_service or AgentService()
        self._registry = registry_service or RegistryService()

    async def register_cron(self, session: AsyncSession, agent_version_id: UUID, trigger: CronTrigger, tenant_id: UUID) -> None:
        registration = AgentTriggerRegistration(
            tenant_id=tenant_id,
            agent_version_id=agent_version_id,
            trigger_type="cron",
            trigger_config=trigger.model_dump(mode="json"),
            status="active",
        )
        session.add(registration)
        await session.flush()

    async def deregister_cron(self, session: AsyncSession, agent_version_id: UUID) -> None:
        registrations = (
            await session.execute(
                select(AgentTriggerRegistration).where(
                    AgentTriggerRegistration.agent_version_id == agent_version_id,
                    AgentTriggerRegistration.trigger_type == "cron",
                )
            )
        ).scalars().all()
        for registration in registrations:
            registration.status = "deregistered"
        await session.flush()

    async def execute_cron_run(self, session: AsyncSession, agent_version_id: UUID, now: datetime | None = None):
        registration = await session.scalar(
            select(AgentTriggerRegistration).where(
                AgentTriggerRegistration.agent_version_id == agent_version_id,
                AgentTriggerRegistration.trigger_type == "cron",
                AgentTriggerRegistration.status == "active",
            )
        )
        if registration is None:
            return None

        trigger = CronTrigger.model_validate(registration.trigger_config)
        if trigger.max_runs is not None and registration.runs_count >= trigger.max_runs:
            registration.status = "deregistered"
            await session.flush()
            return None

        version_info = await self._lookup_version(session, agent_version_id, registration.tenant_id)
        request_context = self._build_service_context(
            registration.tenant_id,
            user_id=version_info.created_by,
            now=now,
        )
        result = await self._agents.run_agent(
            session=session,
            request=AgentRunRequest(agent_name=version_info.name, agent_version=version_info.version, input={}),
            context=request_context,
        )
        registration.runs_count += 1
        registration.last_run_at = request_context.now_utc
        if trigger.max_runs is not None and registration.runs_count >= trigger.max_runs:
            registration.status = "deregistered"
        await session.flush()
        return result

    async def run_due_cron_triggers(self, session: AsyncSession, tenant_id: UUID, now: datetime | None = None) -> list:
        effective_now = now or datetime.now(UTC)
        registrations = (
            await session.execute(
                select(AgentTriggerRegistration).where(
                    AgentTriggerRegistration.tenant_id == tenant_id,
                    AgentTriggerRegistration.trigger_type == "cron",
                    AgentTriggerRegistration.status == "active",
                )
            )
        ).scalars().all()
        results = []
        for registration in registrations:
            trigger = CronTrigger.model_validate(registration.trigger_config)
            if self._matches_cron(trigger.cron_expression, effective_now):
                result = await self.execute_cron_run(session, registration.agent_version_id, now=effective_now)
                if result is not None:
                    results.append(result)
        return results

    def _build_service_context(self, tenant_id: UUID, *, user_id: UUID, now: datetime | None) -> RequestContext:
        effective_now = now or datetime.now(UTC)
        identity = UserIdentity(
            user_id=user_id,
            tenant_id=tenant_id,
            okta_sub=f"service:{tenant_id}",
            email=f"service+{tenant_id}@example.com",
            display_name="AURA Service Identity",
            roles=["service"],
            group_ids=[],
            is_service_identity=True,
        )
        return RequestContext(
            request_id=str(uuid4()),
            trace_id=str(uuid4()),
            tenant_id=tenant_id,
            identity=identity,
            now_utc=effective_now,
        )

    async def _lookup_version(self, session: AsyncSession, agent_version_id: UUID, tenant_id: UUID):
        versions = await self._registry.list_versions(session, tenant_id)
        for version in versions:
            if version.id == agent_version_id:
                return version
        raise ValueError(f"Agent version {agent_version_id} not found.")

    def _matches_cron(self, expression: str, now: datetime) -> bool:
        minute, hour, day, month, weekday = expression.split()
        values = [now.minute, now.hour, now.day, now.month, (now.weekday() + 1) % 7]
        for token, value in zip((minute, hour, day, month, weekday), values, strict=True):
            if token == "*":
                continue
            if token.startswith("*/"):
                step = int(token[2:])
                if value % step != 0:
                    return False
                continue
            if int(token) != value:
                return False
        return True
