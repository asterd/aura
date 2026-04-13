from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.domain.contracts import RequestContext, UserIdentity
from aura.domain.models import Group, User, UserGroupMembership


@dataclass(slots=True)
class ValidatedClaims:
    tenant_id: UUID
    okta_sub: str
    email: str
    display_name: str | None
    roles: list[str]
    groups: list[str]


class JwksCache:
    def __init__(self, ttl: timedelta = timedelta(hours=1)) -> None:
        self._ttl = ttl
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._keys: list[dict[str, object]] = []

    async def get_keys(self) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        if self._keys and now < self._expires_at:
            return self._keys

        timeout = httpx.Timeout(settings.service_check_timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(str(settings.okta_jwks_url))
            response.raise_for_status()
        payload = response.json()
        self._keys = list(payload.get("keys", []))
        self._expires_at = now + self._ttl
        return self._keys

    async def get_signing_key(self, token: str) -> object:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        keys = await self.get_keys()

        matching_key: dict[str, object] | None = None
        if kid is not None:
            matching_key = next((key for key in keys if key.get("kid") == kid), None)
        if matching_key is None and len(keys) == 1:
            matching_key = keys[0]
        if matching_key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token signing key.")
        return jwt.algorithms.get_default_algorithms()[header["alg"]].from_jwk(json.dumps(matching_key))


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


def _extract_tenant_id(claims: dict[str, object]) -> UUID:
    for field_name in ("tenant_id", "tid"):
        raw_value = claims.get(field_name)
        if raw_value:
            try:
                return UUID(str(raw_value))
            except ValueError as exc:
                raise _unauthorized("Invalid tenant claim.") from exc
    raise _unauthorized("Missing tenant claim.")


async def validate_jwt(token: str) -> ValidatedClaims:
    try:
        signing_key = await jwks_cache.get_signing_key(token)
        claims = jwt.decode(
            token,
            key=signing_key,
            algorithms=["HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            issuer=settings.okta_issuer,
            audience=settings.okta_audience,
            options={"require": ["exp", "iss", "aud", "sub", "email"]},
        )
    except (InvalidTokenError, httpx.HTTPError, KeyError, ValueError) as exc:
        raise _unauthorized() from exc

    return ValidatedClaims(
        tenant_id=_extract_tenant_id(claims),
        okta_sub=str(claims["sub"]),
        email=str(claims["email"]),
        display_name=str(claims["name"]) if claims.get("name") else None,
        roles=_as_string_list(claims.get("roles")),
        groups=_as_string_list(claims.get("groups")),
    )


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
    session.add_all(
        UserGroupMembership(user_id=user_id, group_id=group_id)
        for group_id in group_ids
    )


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
