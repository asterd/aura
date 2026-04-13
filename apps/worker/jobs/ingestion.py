from __future__ import annotations

from uuid import UUID

from arq import Retry

from aura.adapters.connectors.base import ConnectorAclError, ConnectorAuthError, ConnectorUnavailableError
from aura.domain.contracts import JobPayload
from aura.services.connector_sync_service import ConnectorSyncService
from aura.services.ingestion_service import IngestionService
from aura.utils.secrets import CredentialResolutionError


ingestion_service = IngestionService()
connector_sync_service = ConnectorSyncService()


async def ingest_document_job(ctx: dict, payload: dict, document_id: str) -> None:
    job_payload = JobPayload.model_validate(payload)
    try:
        await ingestion_service.ingest_document(payload=job_payload, document_id=UUID(document_id))
    except Exception:
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=30 * (2 ** (job_try - 1)))
        raise


async def connector_sync_job(ctx: dict, payload: dict, datasource_id: str, secret_ref: str) -> None:
    job_payload = JobPayload.model_validate(payload)
    datasource_uuid = UUID(datasource_id)
    try:
        await connector_sync_service.sync_datasource(
            payload=job_payload,
            datasource_id=datasource_uuid,
            secret_ref=secret_ref,
        )
    except (ConnectorAuthError, CredentialResolutionError):
        await connector_sync_service.mark_auth_error(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
    except ConnectorAclError:
        await connector_sync_service.mark_failure(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
    except ConnectorUnavailableError:
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=120 * (2 ** (job_try - 1)))
        await connector_sync_service.mark_failure(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
    except Exception:
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=120 * (2 ** (job_try - 1)))
        await connector_sync_service.mark_failure(tenant_id=job_payload.tenant_id, datasource_id=datasource_uuid)
        raise
