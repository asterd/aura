from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from aura.adapters.db.models import AgentRun
from aura.adapters.s3.client import S3Client
from aura.domain.contracts import RequestContext


router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


class SignedUrlResponse(BaseModel):
    url: str


def _parse_s3_ref(ref: str) -> tuple[str, str]:
    if not ref.startswith("s3://"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported artifact ref.")
    bucket_and_key = ref.removeprefix("s3://")
    bucket, _, key = bucket_and_key.partition("/")
    if not bucket or not key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid artifact ref.")
    return bucket, key


@router.get("/signed-url", response_model=SignedUrlResponse)
async def get_signed_url(
    ref: str = Query(..., description="Artifact ref, e.g. s3://bucket/key"),
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> SignedUrlResponse:
    owns_artifact = await session.scalar(
        select(AgentRun.id).where(
            AgentRun.tenant_id == context.tenant_id,
            AgentRun.user_id == context.identity.user_id,
            AgentRun.artifact_refs.any(ref),
        )
    )
    if owns_artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")

    bucket, key = _parse_s3_ref(ref)
    url = await S3Client().get_presigned_url(bucket=bucket, key=key, expires_in=900)
    return SignedUrlResponse(url=url)
