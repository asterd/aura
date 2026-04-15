from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import AgentTriggerRegistration
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import EventTrigger, InternalEvent
from aura.services.registry_service import RegistryService
from aura.utils.secrets import EnvSecretStore


class EventDispatcherService:
    def __init__(
        self,
        *,
        registry_service: RegistryService | None = None,
    ) -> None:
        self._registry = registry_service or RegistryService()

    async def publish(self, tenant_id, event: InternalEvent) -> None:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await redis.publish(f"aura:events:{tenant_id}:{event.event_type}", event.model_dump_json())
        finally:
            await redis.aclose()

    async def dispatch(self, session: AsyncSession, event: InternalEvent) -> list[str]:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            return await self._dispatch_with_redis(session=session, event=event, redis=redis)
        finally:
            await redis.aclose()

    async def _dispatch_with_redis(self, session: AsyncSession, event: InternalEvent, redis: ArqRedis) -> list[str]:
        registrations = (
            await session.execute(
                select(AgentTriggerRegistration).where(
                    AgentTriggerRegistration.tenant_id == event.tenant_id,
                    AgentTriggerRegistration.trigger_type == "event",
                    AgentTriggerRegistration.status == "active",
                )
            )
        ).scalars().all()
        versions = {version.id: version for version in await self._registry.list_versions(session, event.tenant_id)}
        job_ids: list[str] = []
        for registration in registrations:
            trigger = EventTrigger.model_validate(registration.trigger_config)
            if trigger.event_type != event.event_type:
                continue
            if trigger.space_ids and event.source_space_id not in trigger.space_ids:
                continue
            if trigger.filter_tags and not set(trigger.filter_tags).intersection(event.tags):
                continue
            version = versions.get(registration.agent_version_id)
            if version is None or version.status != "published":
                continue
            job = await redis.enqueue_job(
                "execute_event_triggered_run",
                str(event.tenant_id),
                {"agent_version_id": str(version.id), **event.model_dump(mode="json")},
            )
            if job is not None:
                job_ids.append(job.job_id)
        return job_ids

    async def subscribe_and_dispatch(self) -> None:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            pubsub = redis.pubsub()
            await pubsub.psubscribe("aura:events:*")
            async for message in pubsub.listen():
                if message.get("type") not in {"message", "pmessage"}:
                    continue
                event = InternalEvent.model_validate_json(
                    message["data"] if isinstance(message["data"], str) else json.dumps(message["data"])
                )
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        await set_tenant_rls(session, event.tenant_id)
                        await self._dispatch_with_redis(session=session, event=event, redis=redis)
        finally:
            await redis.aclose()

    async def resolve_webhook_target(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        agent_name: str,
        body: bytes,
        signature: str,
    ) -> InternalEvent:
        versions = [version for version in await self._registry.list_versions(session, tenant_id) if version.name == agent_name]
        if not versions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

        for version in versions:
            if version.status != "published":
                continue
            for trigger_payload in version.triggers:
                if trigger_payload.get("type") != "event":
                    continue
                trigger = EventTrigger.model_validate(trigger_payload)
                if trigger.event_type != "webhook.inbound" or not trigger.webhook_secret_ref:
                    continue
                secret = await EnvSecretStore().get(trigger.webhook_secret_ref)
                expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
                if hmac.compare_digest(expected, signature):
                    return InternalEvent(
                        tenant_id=tenant_id,
                        event_type="webhook.inbound",
                        payload=json.loads(body.decode("utf-8")),
                        occurred_at=datetime.now(UTC),
                    )

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
