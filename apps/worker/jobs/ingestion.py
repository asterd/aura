from __future__ import annotations

import logging
from uuid import UUID

from arq import Retry

from aura.adapters.connectors.base import ConnectorAclError, ConnectorAuthError, ConnectorUnavailableError
from aura.domain.contracts import JobPayload
from aura.services.connector_sync_service import ConnectorSyncService
from aura.services.ingestion_service import IngestionService
from aura.utils.observability import record_job_failure, record_job_success, record_trace_event, set_current_trace_id
from aura.utils.secrets import CredentialResolutionError


logger = logging.getLogger("aura")

ingestion_service = IngestionService()
connector_sync_service = ConnectorSyncService()


async def ingest_document_job(ctx: dict, payload: dict, document_id: str) -> None:
    job_payload = JobPayload.model_validate(payload)
    set_current_trace_id(job_payload.trace_id)
    logger.info("worker_job_started job_type=ingestion trace_id=%s resource_id=%s", job_payload.trace_id, document_id)
    record_trace_event(job_payload.trace_id or "", f"ingest_document_job:{document_id}:started")
    try:
        await ingestion_service.ingest_document(payload=job_payload, document_id=UUID(document_id))
        record_job_success(job_type="ingestion", queue="default")
        logger.info("worker_job_completed job_type=ingestion trace_id=%s resource_id=%s", job_payload.trace_id, document_id)
        record_trace_event(job_payload.trace_id or "", f"ingest_document_job:{document_id}:completed")
    except Exception:
        record_job_failure(job_type="ingestion", queue="default")
        logger.exception("worker_job_failed job_type=ingestion trace_id=%s resource_id=%s", job_payload.trace_id, document_id)
        record_trace_event(job_payload.trace_id or "", f"ingest_document_job:{document_id}:failed")
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=30 * (2 ** (job_try - 1)))
        raise


async def connector_sync_job(ctx: dict, payload: dict, datasource_id: str, secret_ref: str) -> None:
    job_payload = JobPayload.model_validate(payload)
    datasource_uuid = UUID(datasource_id)
    set_current_trace_id(job_payload.trace_id)
    logger.info("worker_job_started job_type=connector-sync trace_id=%s resource_id=%s", job_payload.trace_id, datasource_id)
    record_trace_event(job_payload.trace_id or "", f"connector_sync_job:{datasource_id}:started")
    try:
        await connector_sync_service.sync_datasource(
            payload=job_payload,
            datasource_id=datasource_uuid,
            secret_ref=secret_ref,
        )
        record_job_success(job_type="connector-sync", queue="default")
        logger.info("worker_job_completed job_type=connector-sync trace_id=%s resource_id=%s", job_payload.trace_id, datasource_id)
        record_trace_event(job_payload.trace_id or "", f"connector_sync_job:{datasource_id}:completed")
    except (ConnectorAuthError, CredentialResolutionError):
        record_job_failure(job_type="connector-sync", queue="default")
        logger.exception("worker_job_failed job_type=connector-sync trace_id=%s resource_id=%s", job_payload.trace_id, datasource_id)
        await connector_sync_service.mark_auth_error(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
    except ConnectorAclError:
        record_job_failure(job_type="connector-sync", queue="default")
        logger.exception("worker_job_failed job_type=connector-sync trace_id=%s resource_id=%s", job_payload.trace_id, datasource_id)
        await connector_sync_service.mark_failure(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
    except ConnectorUnavailableError:
        record_job_failure(job_type="connector-sync", queue="default")
        logger.warning("worker_job_retry job_type=connector-sync trace_id=%s resource_id=%s", job_payload.trace_id, datasource_id)
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=120 * (2 ** (job_try - 1)))
        await connector_sync_service.mark_failure(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
    except Exception:
        record_job_failure(job_type="connector-sync", queue="default")
        logger.exception("worker_job_failed job_type=connector-sync trace_id=%s resource_id=%s", job_payload.trace_id, datasource_id)
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=120 * (2 ** (job_try - 1)))
        await connector_sync_service.mark_failure(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
