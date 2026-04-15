from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field, SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import require_identity
from apps.api.dependencies.db import get_db_session, get_unscoped_db_session
from aura.adapters.db.models import LocalAuthUser, User
from aura.domain.contracts import UserIdentity
from aura.services.identity import issue_local_access_token
from aura.utils.passwords import hash_password, verify_password


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


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


class ProfileResponse(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    roles: list[str]
    tenant_id: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.patch("/me", response_model=ProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """Aggiorna il profilo dell'utente corrente."""
    if payload.display_name is not None:
        await session.execute(
            update(User)
            .where(User.id == identity.user_id)
            .values(display_name=payload.display_name)
        )
        await session.flush()
    user = await session.get(User, identity.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ProfileResponse(
        user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        roles=identity.roles,
        tenant_id=str(identity.tenant_id),
    )


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Cambio password per utenti local-auth. Noop per Okta."""
    local_user = await session.scalar(
        select(LocalAuthUser).where(
            LocalAuthUser.tenant_id == identity.tenant_id,
            LocalAuthUser.email == identity.email.lower(),
            LocalAuthUser.is_active.is_(True),
        )
    )
    if local_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change not available for this auth mode",
        )
    if not verify_password(payload.current_password, local_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    await session.execute(
        update(LocalAuthUser)
        .where(LocalAuthUser.id == local_user.id)
        .values(password_hash=hash_password(payload.new_password))
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
