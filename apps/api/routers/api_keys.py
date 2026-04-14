from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import require_identity
from apps.api.dependencies.db import get_db_session
from aura.domain.contracts import UserIdentity
from aura.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/api/v1/admin/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str
    scopes: list[str] = []
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class CreateApiKeyResponse(ApiKeyResponse):
    raw_key: str


@router.post("", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: CreateApiKeyRequest,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> CreateApiKeyResponse:
    svc = ApiKeyService()
    record, raw_key = await svc.create(
        session,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        name=payload.name,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    return CreateApiKeyResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        scopes=record.scopes,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
        raw_key=raw_key,
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApiKeyResponse]:
    svc = ApiKeyService()
    keys = await svc.list_keys(session, identity.tenant_id)
    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            prefix=k.prefix,
            scopes=k.scopes,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    svc = ApiKeyService()
    ok = await svc.revoke(session, key_id, identity.tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
