from __future__ import annotations

from uuid import UUID

from arq import Retry

from aura.domain.contracts import JobPayload
from aura.services.ingestion_service import IngestionService


ingestion_service = IngestionService()


async def ingest_document_job(ctx: dict, payload: dict, document_id: str) -> None:
    job_payload = JobPayload.model_validate(payload)
    try:
        await ingestion_service.ingest_document(payload=job_payload, document_id=UUID(document_id))
    except Exception:
        job_try = int(ctx.get("job_try") or 1)
        if job_try < 3:
            raise Retry(defer=30 * (2 ** (job_try - 1)))
        raise
