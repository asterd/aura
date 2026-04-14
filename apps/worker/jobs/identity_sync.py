from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from arq import Retry
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from apps.api.config import settings
from aura.adapters.db.models import Tenant
from aura.adapters.db.session import AsyncSessionLocal
from aura.domain.contracts import JobPayload
from aura.services.identity_sync_service import IdentitySyncService
from aura.utils.observability import record_job_failure, record_job_success, record_trace_event, set_current_trace_id


identity_sync_service = IdentitySyncService()


async def identity_sync_job(ctx: dict, payload: dict, tenant_id: str) -> dict:
    job_payload = JobPayload.model_validate(payload)
    set_current_trace_id(job_payload.trace_id)
    record_trace_event(job_payload.trace_id or "", f"identity_sync_job:{tenant_id}:started")
    try:
        result = await identity_sync_service.sync_tenant(tenant_id=UUID(tenant_id))
    except Exception:
        record_job_failure(job_type="identity-sync", queue="default")
        record_trace_event(job_payload.trace_id or "", f"identity_sync_job:{tenant_id}:failed")
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 5:
            raise Retry(defer=60 * (2 ** (job_try - 1)))
        raise
    record_job_success(job_type="identity-sync", queue="default")
    record_trace_event(job_payload.trace_id or "", f"identity_sync_job:{tenant_id}:completed")
    return result.model_dump(mode="json")


async def schedule_identity_sync_job(ctx: dict) -> None:
    async with AsyncSessionLocal() as session:
        tenant_ids = list(
            (await session.execute(select(Tenant.id).where(Tenant.status == "active"))).scalars()
        )

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        scheduled_at = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
        for tenant_id in tenant_ids:
            payload = JobPayload(
                tenant_id=tenant_id,
                job_key=f"identity-sync:{tenant_id}:{scheduled_at}",
                trace_id=f"identity-sync:{tenant_id}:{scheduled_at}",
            )
            await redis.enqueue_job(
                "identity_sync_job",
                payload.model_dump(mode="json"),
                str(tenant_id),
                _job_id=f"identity-sync:{tenant_id}:{scheduled_at}",
            )
    finally:
        await redis.aclose()
