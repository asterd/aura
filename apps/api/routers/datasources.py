from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import datasource_service
from aura.domain.contracts import RequestContext


router = APIRouter(prefix="/api/v1/datasources", tags=["datasources"])


class UploadDatasourceResponse(BaseModel):
    datasource_id: UUID
    document_id: UUID
    job_id: UUID


@router.post("/upload", response_model=UploadDatasourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_datasource(
    background_tasks: BackgroundTasks,
    space_id: UUID = Form(...),
    file: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> UploadDatasourceResponse:
    data = await file.read()
    result = await datasource_service.upload(
        session=session,
        context=context,
        space_id=space_id,
        filename=file.filename or "",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        bucket_name=settings.s3_bucket_name,
        background_tasks=background_tasks,
    )
    return UploadDatasourceResponse(
        datasource_id=result.datasource_id,
        document_id=result.document_id,
        job_id=result.job_id,
    )
