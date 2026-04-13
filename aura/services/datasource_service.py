from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import Datasource, Document
from aura.adapters.s3.client import S3Client
from aura.domain.contracts import JobPayload, RequestContext
from aura.services.space_service import SpaceService


@dataclass(slots=True)
class UploadResult:
    datasource_id: UUID
    document_id: UUID
    job_id: UUID


class DatasourceService:
    def __init__(self, *, s3_client: S3Client | None = None, space_service: SpaceService | None = None) -> None:
        self._s3 = s3_client or S3Client()
        self._space_service = space_service or SpaceService()

    async def upload(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        space_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
        bucket_name: str,
        background_tasks: BackgroundTasks,
    ) -> UploadResult:
        if not filename:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Filename is required.")

        space = await self._space_service.require_membership(session, context.identity, space_id)
        extension = Path(filename).suffix
        original_key = f"originals/{context.tenant_id}/{space.id}/{uuid4()}{extension}"
        source_url = await self._s3.upload_file(bucket_name, original_key, data, content_type)

        datasource = Datasource(
            tenant_id=context.tenant_id,
            space_id=space.id,
            connector_type="file_upload",
            display_name=filename,
            credentials_ref="upload://direct",
        )
        session.add(datasource)
        await session.flush()

        document = Document(
            tenant_id=context.tenant_id,
            space_id=space.id,
            datasource_id=datasource.id,
            external_id=original_key,
            title=filename,
            source_path=filename,
            source_url=source_url,
            content_type=content_type or "application/octet-stream",
            status="discovered",
        )
        session.add(document)
        await session.flush()

        job_id = uuid5(NAMESPACE_URL, f"ingest:{document.id}")
        payload = JobPayload(
            tenant_id=context.tenant_id,
            job_key=f"ingest:{document.id}:pending",
            requested_by_user_id=context.identity.user_id,
            trace_id=context.trace_id,
        )
        background_tasks.add_task(
            self._enqueue_ingest_job,
            job_id=job_id,
            payload=payload,
            document_id=document.id,
        )

        return UploadResult(datasource_id=datasource.id, document_id=document.id, job_id=job_id)

    async def _enqueue_ingest_job(self, *, job_id: UUID, payload: JobPayload, document_id: UUID) -> None:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await redis.enqueue_job(
                "ingest_document_job",
                payload.model_dump(mode="json"),
                str(document_id),
                _job_id=str(job_id),
            )
        finally:
            await redis.aclose()
