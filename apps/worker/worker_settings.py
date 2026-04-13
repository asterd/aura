from __future__ import annotations

from arq.connections import RedisSettings

from apps.api.config import settings


async def ingest_document_job(ctx: dict) -> None:
    raise NotImplementedError("Document ingestion is implemented in a later phase.")


async def agent_run_job(ctx: dict) -> None:
    raise NotImplementedError("Agent runtime execution is implemented in a later phase.")


class WorkerSettings:
    functions = [ingest_document_job, agent_run_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    allow_abort_jobs = True
    job_completion_wait = 5
