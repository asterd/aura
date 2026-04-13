from __future__ import annotations

from arq.worker import func
from arq.connections import RedisSettings

from apps.api.config import settings
from apps.worker.jobs.ingestion import ingest_document_job


async def agent_run_job(ctx: dict) -> None:
    raise NotImplementedError("Agent runtime execution is implemented in a later phase.")


class WorkerSettings:
    functions = [func(ingest_document_job, max_tries=3, timeout=300), agent_run_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    allow_abort_jobs = True
    job_completion_wait = 5
