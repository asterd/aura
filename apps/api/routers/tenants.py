from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.dependencies.auth import get_request_context
from aura.adapters.db.session import set_tenant_rls
from apps.api.dependencies.db import get_db_session, get_unscoped_db_session
from aura.adapters.db.models import LocalAuthUser, Tenant
from aura.domain.contracts import RequestContext
from aura.utils.passwords import hash_password


router = APIRouter(prefix="/api/v1/admin/tenants", tags=["tenants"])


class ProvisionTenantRequest(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]{3,64}$")
    display_name: str
    auth_mode: str = Field(pattern=r"^(okta|local)$")
    okta_org_id: str | None = None
    okta_jwks_url: str | None = None
    okta_issuer: str | None = None
    okta_audience: str | None = None
    admin_email: EmailStr | None = None
    admin_password: SecretStr | None = None
    admin_display_name: str | None = None


class ProvisionTenantResponse(BaseModel):
    tenant_id: UUID
    slug: str
    display_name: str
    auth_mode: str
    bootstrap_admin_created: bool


class TenantResponse(BaseModel):
    tenant_id: UUID
    slug: str
    display_name: str
    auth_mode: str
    okta_org_id: str | None = None
    okta_jwks_url: str | None = None
    okta_issuer: str | None = None
    okta_audience: str | None = None
    status: str


class UpdateTenantAuthRequest(BaseModel):
    display_name: str | None = None
    auth_mode: str | None = Field(default=None, pattern=r"^(okta|local)$")
    okta_org_id: str | None = None
    okta_jwks_url: str | None = None
    okta_issuer: str | None = None
    okta_audience: str | None = None
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_display_name: str | None = None


class LocalAuthUserResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str | None = None
    roles: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateLocalAuthUserRequest(BaseModel):
    email: EmailStr
    password: SecretStr
    display_name: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["user"])


class UpdateLocalAuthUserRequest(BaseModel):
    display_name: str | None = None
    password: SecretStr | None = None
    roles: list[str] | None = None
    is_active: bool | None = None


def _require_bootstrap_token(token: str | None) -> None:
    if token == settings.bootstrap_token.get_secret_value():
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token.")


def _require_tenant_admin(context: RequestContext) -> None:
    if set(context.identity.roles).intersection({"admin", "tenant_admin", "platform_admin"}):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role required.")


def _serialize_tenant(tenant: Tenant) -> TenantResponse:
    return TenantResponse(
        tenant_id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        auth_mode=tenant.auth_mode,
        okta_org_id=tenant.okta_org_id,
        okta_jwks_url=tenant.okta_jwks_url,
        okta_issuer=tenant.okta_issuer,
        okta_audience=tenant.okta_audience,
        status=tenant.status,
    )


def _serialize_local_user(user: LocalAuthUser) -> LocalAuthUserResponse:
    return LocalAuthUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=list(user.roles or []),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _ensure_unique_okta_org_id(session: AsyncSession, okta_org_id: str | None, current_tenant_id: UUID | None = None) -> None:
    if not okta_org_id:
        return
    existing = await session.scalar(select(Tenant).where(Tenant.okta_org_id == okta_org_id))
    if existing is None:
        return
    if current_tenant_id is not None and existing.id == current_tenant_id:
        return
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="okta_org_id already assigned to another tenant.")


@router.post("/provision", response_model=ProvisionTenantResponse, status_code=status.HTTP_201_CREATED)
async def provision_tenant(
    request: ProvisionTenantRequest,
    x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    session: AsyncSession = Depends(get_unscoped_db_session),
) -> ProvisionTenantResponse:
    _require_bootstrap_token(x_bootstrap_token)

    if request.auth_mode == "local":
        if request.admin_email is None or request.admin_password is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Local auth tenants require admin_email and admin_password.",
            )
    if request.auth_mode == "okta":
        if request.okta_jwks_url is None and request.okta_org_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Okta tenants require okta_jwks_url or okta_org_id.",
            )

    existing = await session.scalar(select(Tenant).where(Tenant.slug == request.slug))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already exists.")
    await _ensure_unique_okta_org_id(session, request.okta_org_id)

    tenant_id = uuid4()
    await set_tenant_rls(session, tenant_id)
    tenant = Tenant(
        id=tenant_id,
        slug=request.slug,
        display_name=request.display_name,
        okta_org_id=request.okta_org_id,
        auth_mode=request.auth_mode,
        okta_jwks_url=request.okta_jwks_url,
        okta_issuer=request.okta_issuer,
        okta_audience=request.okta_audience,
        status="active",
    )
    session.add(tenant)
    await session.flush()

    bootstrap_admin_created = False
    if request.auth_mode == "local" and request.admin_email and request.admin_password:
        local_admin = LocalAuthUser(
            tenant_id=tenant.id,
            email=request.admin_email.lower(),
            password_hash=hash_password(request.admin_password.get_secret_value()),
            display_name=request.admin_display_name or request.admin_email.split("@", 1)[0],
            roles=["admin", "tenant_admin"],
            is_active=True,
            updated_at=datetime.now(UTC),
        )
        session.add(local_admin)
        bootstrap_admin_created = True
        await session.flush()

    return ProvisionTenantResponse(
        tenant_id=tenant.id,
        slug=tenant.slug,
        display_name=tenant.display_name,
        auth_mode=tenant.auth_mode,
        bootstrap_admin_created=bootstrap_admin_created,
    )


@router.get("/current", response_model=TenantResponse)
async def get_current_tenant(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    _require_tenant_admin(context)
    tenant = await session.scalar(select(Tenant).where(Tenant.id == context.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return _serialize_tenant(tenant)


@router.patch("/current/auth", response_model=TenantResponse)
async def update_current_tenant_auth(
    request: UpdateTenantAuthRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> TenantResponse:
    _require_tenant_admin(context)
    tenant = await session.scalar(select(Tenant).where(Tenant.id == context.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    target_auth_mode = request.auth_mode or tenant.auth_mode
    if target_auth_mode == "okta" and not (request.okta_jwks_url or tenant.okta_jwks_url or request.okta_org_id or tenant.okta_org_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Okta auth requires okta_jwks_url or okta_org_id.",
        )
    await _ensure_unique_okta_org_id(
        session,
        request.okta_org_id if request.okta_org_id is not None else tenant.okta_org_id,
        current_tenant_id=tenant.id,
    )
    if target_auth_mode == "local":
        existing_local_user = await session.scalar(
            select(LocalAuthUser).where(LocalAuthUser.tenant_id == tenant.id, LocalAuthUser.is_active.is_(True))
        )
        if existing_local_user is None and (request.bootstrap_admin_email is None or request.bootstrap_admin_password is None):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Switching to local auth requires an active local admin or bootstrap_admin credentials.",
            )

    if request.display_name is not None:
        tenant.display_name = request.display_name
    tenant.auth_mode = target_auth_mode
    tenant.okta_org_id = request.okta_org_id if request.okta_org_id is not None else tenant.okta_org_id
    tenant.okta_jwks_url = request.okta_jwks_url if request.okta_jwks_url is not None else tenant.okta_jwks_url
    tenant.okta_issuer = request.okta_issuer if request.okta_issuer is not None else tenant.okta_issuer
    tenant.okta_audience = request.okta_audience if request.okta_audience is not None else tenant.okta_audience

    if target_auth_mode == "local":
        existing_local_user = await session.scalar(
            select(LocalAuthUser).where(LocalAuthUser.tenant_id == tenant.id, LocalAuthUser.is_active.is_(True))
        )
        if existing_local_user is None and request.bootstrap_admin_email and request.bootstrap_admin_password:
            session.add(
                LocalAuthUser(
                    tenant_id=tenant.id,
                    email=request.bootstrap_admin_email.lower(),
                    password_hash=hash_password(request.bootstrap_admin_password.get_secret_value()),
                    display_name=request.bootstrap_admin_display_name or request.bootstrap_admin_email.split("@", 1)[0],
                    roles=["admin", "tenant_admin"],
                    is_active=True,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.flush()

    return _serialize_tenant(tenant)


@router.get("/local-users", response_model=list[LocalAuthUserResponse])
async def list_local_users(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[LocalAuthUserResponse]:
    _require_tenant_admin(context)
    tenant = await session.scalar(select(Tenant).where(Tenant.id == context.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    if tenant.auth_mode != "local":
        return []
    rows = await session.execute(
        select(LocalAuthUser)
        .where(LocalAuthUser.tenant_id == context.tenant_id)
        .order_by(LocalAuthUser.email)
    )
    return [_serialize_local_user(user) for user in rows.scalars().all()]


@router.post("/local-users", response_model=LocalAuthUserResponse, status_code=status.HTTP_201_CREATED)
async def create_local_user(
    request: CreateLocalAuthUserRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> LocalAuthUserResponse:
    _require_tenant_admin(context)
    tenant = await session.scalar(select(Tenant).where(Tenant.id == context.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    if tenant.auth_mode != "local":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Local users are available only for local-auth tenants.")
    existing = await session.scalar(
        select(LocalAuthUser).where(LocalAuthUser.tenant_id == context.tenant_id, LocalAuthUser.email == request.email.lower())
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Local user already exists.")
    user = LocalAuthUser(
        tenant_id=context.tenant_id,
        email=request.email.lower(),
        password_hash=hash_password(request.password.get_secret_value()),
        display_name=request.display_name or request.email.split("@", 1)[0],
        roles=request.roles or ["user"],
        is_active=True,
        updated_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return _serialize_local_user(user)


@router.patch("/local-users/{user_id}", response_model=LocalAuthUserResponse)
async def update_local_user(
    user_id: UUID,
    request: UpdateLocalAuthUserRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> LocalAuthUserResponse:
    _require_tenant_admin(context)
    user = await session.scalar(
        select(LocalAuthUser).where(LocalAuthUser.id == user_id, LocalAuthUser.tenant_id == context.tenant_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local user not found.")
    if request.display_name is not None:
        user.display_name = request.display_name
    if request.password is not None:
        user.password_hash = hash_password(request.password.get_secret_value())
    if request.roles is not None:
        user.roles = request.roles
    if request.is_active is not None:
        user.is_active = request.is_active
    user.updated_at = datetime.now(UTC)
    await session.flush()
    return _serialize_local_user(user)
