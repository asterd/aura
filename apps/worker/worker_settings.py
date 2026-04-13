from __future__ import annotations

from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func

from apps.api.config import settings
from apps.worker.jobs.agents import agent_run_job, dispatch_registered_crons_job, execute_event_triggered_run
from apps.worker.jobs.identity_sync import identity_sync_job, schedule_identity_sync_job
from apps.worker.jobs.ingestion import connector_sync_job, ingest_document_job

class WorkerSettings:
    functions = [
        func(ingest_document_job, max_tries=3, timeout=300),
        func(connector_sync_job, max_tries=3, timeout=600),
        func(identity_sync_job, max_tries=5, timeout=600),
        func(schedule_identity_sync_job, max_tries=1, timeout=300),
        func(agent_run_job, max_tries=1, timeout=300),
        func(dispatch_registered_crons_job, max_tries=1, timeout=300),
        func(execute_event_triggered_run, max_tries=1, timeout=300),
    ]
    cron_jobs = [cron(schedule_identity_sync_job, minute=0), cron(dispatch_registered_crons_job, second=0)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    allow_abort_jobs = True
    job_completion_wait = 5
