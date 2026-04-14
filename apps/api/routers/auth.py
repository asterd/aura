from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.db import get_unscoped_db_session
from aura.services.identity import issue_local_access_token


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LocalLoginRequest(BaseModel):
    tenant_slug: str
    email: EmailStr
    password: SecretStr


class LocalLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/local/login", response_model=LocalLoginResponse)
async def local_login(
    request: LocalLoginRequest,
    session: AsyncSession = Depends(get_unscoped_db_session),
) -> LocalLoginResponse:
    token = await issue_local_access_token(
        session,
        tenant_slug=request.tenant_slug,
        email=request.email,
        password=request.password.get_secret_value(),
    )
    return LocalLoginResponse(access_token=token)
