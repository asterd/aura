from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast

from apps.api.config import settings
from aura.adapters.db.session import set_tenant_rls
from aura.adapters.db.models import Tenant
from aura.domain.contracts import RequestContext, UserIdentity
from aura.domain.models import Group, LocalAuthUser, User, UserGroupMembership
from aura.utils.passwords import verify_password


@dataclass(slots=True)
class ValidatedClaims:
    tenant_id: UUID
    okta_sub: str
    email: str
    display_name: str | None
    roles: list[str]
    groups: list[str]


@dataclass(slots=True)
class TenantAuthConfig:
    tenant_id: UUID
    slug: str
    auth_mode: str
    issuer: str | None
    audience: str | None
    jwks_url: str | None


class JwksCache:
    def __init__(self, ttl: timedelta = timedelta(hours=1)) -> None:
        self._ttl = ttl
        self._keys_by_url: dict[str, tuple[datetime, list[dict[str, object]]]] = {}
        self._inflight_fetches: dict[tuple[str, int], asyncio.Task[list[dict[str, object]]]] = {}
        self._lock = Lock()

    async def get_keys(self, jwks_url: str | None = None) -> list[dict[str, object]]:
        if jwks_url is None:
            raise TypeError("jwks_url is required")
        now = datetime.now(UTC)
        with self._lock:
            cached = self._keys_by_url.get(jwks_url)
            if cached is not None and now < cached[0]:
                return cached[1]

            loop = asyncio.get_running_loop()
            inflight_key = (jwks_url, id(loop))
            task = self._inflight_fetches.get(inflight_key)
            created_task = task is None
            if task is None:
                task = loop.create_task(self._fetch_keys(jwks_url))
                self._inflight_fetches[inflight_key] = task

        try:
            keys = await task
        except Exception:
            if created_task:
                with self._lock:
                    self._inflight_fetches.pop(inflight_key, None)
            raise

        with self._lock:
            self._keys_by_url[jwks_url] = (datetime.now(UTC) + self._ttl, keys)
            if created_task:
                self._inflight_fetches.pop(inflight_key, None)
        return keys

    async def _fetch_keys(self, jwks_url: str) -> list[dict[str, object]]:
        timeout = httpx.Timeout(settings.service_check_timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
        payload = response.json()
        return list(payload.get("keys", []))

    async def get_signing_key(self, token: str, jwks_url: str) -> object:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        try:
            keys = await self.get_keys(jwks_url)
        except TypeError:
            keys = await self.get_keys()

        matching_key: dict[str, object] | None = None
        if kid is not None:
            matching_key = next((key for key in keys if key.get("kid") == kid), None)
        if matching_key is None and len(keys) == 1:
            matching_key = keys[0]
        if matching_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token signing key.")
        return jwt.algorithms.get_default_algorithms()[str(header["alg"])].from_jwk(json.dumps(matching_key))


jwks_cache = JwksCache()


def _unauthorized(detail: str = "Invalid authentication credentials.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise _unauthorized("Invalid JWT claims.")


def _extract_tenant_id(unverified_claims: dict[str, object]) -> UUID:
    for field_name in ("tenant_id", "tid"):
        raw_value = unverified_claims.get(field_name)
        if raw_value:
            try:
                return UUID(str(raw_value))
            except ValueError as exc:
                raise _unauthorized("Invalid tenant claim.") from exc
    raise _unauthorized("Missing tenant claim.")


async def resolve_tenant_auth_config(session: AsyncSession, tenant_id: UUID) -> TenantAuthConfig:
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise _unauthorized("Unknown tenant.")
    return TenantAuthConfig(
        tenant_id=tenant.id,
        slug=tenant.slug,
        auth_mode=tenant.auth_mode,
        issuer=tenant.okta_issuer or settings.okta_issuer,
        audience=tenant.okta_audience or settings.okta_audience,
        jwks_url=tenant.okta_jwks_url or str(settings.okta_jwks_url),
    )


async def validate_token(session: AsyncSession, token: str) -> ValidatedClaims:
    try:
        unverified_claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    except InvalidTokenError as exc:
        raise _unauthorized() from exc
    tenant_id = _extract_tenant_id(unverified_claims)
    auth_config = await resolve_tenant_auth_config(session, tenant_id)
    if auth_config.auth_mode == "local":
        return _validate_local_token(token, auth_config)
    return await _validate_okta_token(token, auth_config)


def _validate_local_token(token: str, auth_config: TenantAuthConfig) -> ValidatedClaims:
    try:
        claims = jwt.decode(
            token,
            key=settings.local_auth_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=f"{settings.local_auth_jwt_issuer}:{auth_config.slug}",
            audience=settings.local_auth_audience,
            options={"require": ["exp", "iss", "aud", "sub", "email"]},
        )
    except (InvalidTokenError, ValueError) as exc:
        raise _unauthorized() from exc
    return ValidatedClaims(
        tenant_id=auth_config.tenant_id,
        okta_sub=str(claims["sub"]),
        email=str(claims["email"]),
        display_name=str(claims["name"]) if claims.get("name") else None,
        roles=_as_string_list(claims.get("roles")),
        groups=_as_string_list(claims.get("groups")),
    )


async def _validate_okta_token(token: str, auth_config: TenantAuthConfig) -> ValidatedClaims:
    try:
        signing_key = await jwks_cache.get_signing_key(token, auth_config.jwks_url or str(settings.okta_jwks_url))
        claims = jwt.decode(
            token,
            key=cast(str | bytes, signing_key),
            algorithms=["HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            issuer=auth_config.issuer,
            audience=auth_config.audience,
            options={"require": ["exp", "iss", "aud", "sub", "email"]},
        )
    except (InvalidTokenError, httpx.HTTPError, KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    return ValidatedClaims(
        tenant_id=auth_config.tenant_id,
        okta_sub=str(claims["sub"]),
        email=str(claims["email"]),
        display_name=str(claims["name"]) if claims.get("name") else None,
        roles=_as_string_list(claims.get("roles")),
        groups=_as_string_list(claims.get("groups")),
    )


async def issue_local_access_token(
    session: AsyncSession,
    *,
    tenant_slug: str,
    email: str,
    password: str,
    expires_in: timedelta = timedelta(hours=8),
) -> str:
    tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if tenant is None or tenant.auth_mode != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local-auth tenant not found.")
    await set_tenant_rls(session, tenant.id)
    local_user = await session.scalar(
        select(LocalAuthUser).where(
            LocalAuthUser.tenant_id == tenant.id,
            LocalAuthUser.email == email,
            LocalAuthUser.is_active.is_(True),
        )
    )
    if local_user is None or not verify_password(password, local_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    now = datetime.now(UTC)
    payload = {
        "sub": f"local:{email.lower()}",
        "iss": f"{settings.local_auth_jwt_issuer}:{tenant.slug}",
        "aud": settings.local_auth_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "email": email.lower(),
        "tenant_id": str(tenant.id),
        "name": local_user.display_name,
        "roles": list(local_user.roles or []),
        "groups": [],
    }
    return jwt.encode(payload, settings.local_auth_jwt_secret.get_secret_value(), algorithm="HS256")


async def _resolve_group_ids(session: AsyncSession, tenant_id: UUID, claim_groups: list[str]) -> list[UUID]:
    if not claim_groups:
        return []

    result = await session.execute(
        select(Group.id).where(
            Group.tenant_id == tenant_id,
            or_(Group.external_id.in_(claim_groups), Group.display_name.in_(claim_groups)),
        )
    )
    return list(result.scalars())


async def _sync_memberships(session: AsyncSession, user_id: UUID, group_ids: list[UUID]) -> None:
    await session.execute(delete(UserGroupMembership).where(UserGroupMembership.user_id == user_id))
    if not group_ids:
        return
    session.add_all(UserGroupMembership(user_id=user_id, group_id=group_id) for group_id in group_ids)


async def build_request_context(
    session: AsyncSession,
    *,
    claims: ValidatedClaims,
    request_id: str,
    trace_id: str,
) -> RequestContext:
    now = datetime.now(UTC)

    result = await session.execute(
        select(User).where(User.tenant_id == claims.tenant_id, User.okta_sub == claims.okta_sub)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            tenant_id=claims.tenant_id,
            okta_sub=claims.okta_sub,
            email=claims.email,
            display_name=claims.display_name,
            roles=claims.roles,
            synced_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()
    else:
        user.email = claims.email
        user.display_name = claims.display_name
        user.roles = claims.roles
        user.synced_at = now
        user.updated_at = now
        await session.flush()

    group_ids = await _resolve_group_ids(session, claims.tenant_id, claims.groups)
    await _sync_memberships(session, user.id, group_ids)
    await session.flush()

    identity = UserIdentity(
        user_id=user.id,
        tenant_id=claims.tenant_id,
        okta_sub=claims.okta_sub,
        email=claims.email,
        display_name=claims.display_name,
        roles=claims.roles,
        group_ids=group_ids,
        is_service_identity=False,
    )
    return RequestContext(
        request_id=request_id,
        trace_id=trace_id,
        tenant_id=claims.tenant_id,
        identity=identity,
        now_utc=now,
    )
