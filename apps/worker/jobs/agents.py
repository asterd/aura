from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.config import settings
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.adapters.db.models import AgentTriggerRegistration
from aura.domain.contracts import AgentRunRequest, InternalEvent, RequestContext, UserIdentity
from aura.services.agent_service import AgentService
from aura.services.registry_service import RegistryService
from aura.services.trigger_scheduler_service import TriggerSchedulerService
from aura.utils.observability import record_job_failure, record_job_success, record_trace_event


owner_engine = create_async_engine(
    settings.migration_database_url,
    pool_pre_ping=True,
    connect_args={"timeout": settings.postgres_connect_timeout_s},
)
OwnerSessionLocal = async_sessionmaker(owner_engine, expire_on_commit=False)


async def agent_run_job(
    ctx: dict,
    tenant_id: str,
    agent_name: str,
    agent_version: str | None,
    input_data: dict,
    user_id: str | None = None,
) -> None:
    del ctx
    tenant_uuid = UUID(tenant_id)
    trace_id = str(uuid4())
    record_trace_event(trace_id, f"agent_run_job:{agent_name}:started")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, tenant_uuid)
            service = AgentService()
            try:
                await service.run_agent(
                    session=session,
                    request=AgentRunRequest(agent_name=agent_name, agent_version=agent_version, input=input_data),
                    context=_service_context(tenant_uuid, user_id=UUID(user_id) if user_id else uuid4(), trace_id=trace_id),
                )
                record_job_success(job_type="agent-run", queue="default")
                record_trace_event(trace_id, f"agent_run_job:{agent_name}:completed")
            except Exception:
                record_job_failure(job_type="agent-run", queue="default")
                record_trace_event(trace_id, f"agent_run_job:{agent_name}:failed")
                raise


async def dispatch_registered_crons_job(ctx: dict) -> None:
    del ctx
    scheduler = TriggerSchedulerService()
    async with OwnerSessionLocal() as owner_session:
        tenant_rows = await owner_session.execute(
            select(AgentTriggerRegistration.tenant_id)
            .where(
                AgentTriggerRegistration.trigger_type == "cron",
                AgentTriggerRegistration.status == "active",
            )
            .distinct()
        )
        tenants = list(tenant_rows.scalars())

    for tenant_id in tenants:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await set_tenant_rls(session, tenant_id)
                await scheduler.run_due_cron_triggers(session, tenant_id, now=datetime.now(UTC))


async def execute_event_triggered_run(ctx: dict, tenant_id: str, event_payload: dict) -> None:
    del ctx
    tenant_uuid = UUID(tenant_id)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, tenant_uuid)
            event = InternalEvent.model_validate(event_payload)
            version_id = UUID(event_payload["agent_version_id"])
            registration = await session.scalar(
                select(AgentTriggerRegistration).where(
                    AgentTriggerRegistration.tenant_id == tenant_uuid,
                    AgentTriggerRegistration.agent_version_id == version_id,
                    AgentTriggerRegistration.trigger_type == "event",
                    AgentTriggerRegistration.status == "active",
                )
            )
            if registration is None:
                return
            versions = {version.id: version for version in await RegistryService().list_versions(session, tenant_uuid)}
            version = versions.get(version_id)
            if version is None or version.status != "published":
                return
            await AgentService().run_agent(
                session=session,
                request=AgentRunRequest(agent_name=version.name, agent_version=version.version, input=event.payload),
                context=_service_context(tenant_uuid, user_id=version.created_by),
            )
            registration.runs_count += 1
            registration.last_run_at = datetime.now(UTC)


def _service_context(tenant_id: UUID, *, user_id: UUID, trace_id: str | None = None) -> RequestContext:
    now = datetime.now(UTC)
    return RequestContext(
        request_id=str(uuid4()),
        trace_id=trace_id or str(uuid4()),
        tenant_id=tenant_id,
        identity=UserIdentity(
            user_id=user_id,
            tenant_id=tenant_id,
            okta_sub=f"service:{tenant_id}",
            email=f"service+{tenant_id}@example.com",
            display_name="AURA Service Identity",
            roles=["service"],
            group_ids=[],
            is_service_identity=True,
        ),
        now_utc=now,
    )
