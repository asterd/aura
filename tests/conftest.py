from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aura.adapters.db.session import set_tenant_rls
from aura.domain.models import Base, User
from aura.services.identity import JwksCache

# ---------------------------------------------------------------------------
# Test database — uses a separate DB or the same with clean-up.
# Requires TEST_DATABASE_URL env var; defaults to same as DATABASE_URL but
# this can be overridden in CI.
# ---------------------------------------------------------------------------
import os

TEST_DATABASE_URL: str = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ["DATABASE_URL"],
)

test_engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestAsyncSession = async_sessionmaker(test_engine, expire_on_commit=False)

# ---------------------------------------------------------------------------
# Fixed tenant / user UUIDs used across tests
# ---------------------------------------------------------------------------
TENANT_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
TENANT_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")
USER_A_SUB = "okta|user_a"
USER_B_SUB = "okta|user_b"

# ---------------------------------------------------------------------------
# Local RSA key-pair for signing test JWTs — never touches real Okta
# ---------------------------------------------------------------------------
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_KID = "test-key-1"
_ALGORITHM = "RS256"
_ISSUER = "https://test.okta.example.com"
_AUDIENCE = "api://default"


def generate_test_jwt(
    *,
    tenant_id: UUID,
    okta_sub: str = "okta|test_user",
    email: str = "test@example.com",
    roles: list[str] | None = None,
    groups: list[str] | None = None,
    expired: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload = {
        "sub": okta_sub,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "email": email,
        "tenant_id": str(tenant_id),
        "roles": roles or [],
        "groups": groups or [],
    }
    return jwt.encode(
        payload,
        _PRIVATE_KEY,
        algorithm=_ALGORITHM,
        headers={"kid": _KID},
    )


def _build_jwks() -> dict:
    import base64

    pub_numbers = _PUBLIC_KEY.public_numbers()

    def _to_base64url_uint(val: int) -> str:
        length = (val.bit_length() + 7) // 8
        data = val.to_bytes(length, "big")
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": _KID,
                "use": "sig",
                "alg": _ALGORITHM,
                "n": _to_base64url_uint(pub_numbers.n),
                "e": _to_base64url_uint(pub_numbers.e),
            }
        ]
    }


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def patch_jwks_cache():
    """Replace the live JWKS cache with one that uses the local test key."""
    import aura.services.identity as identity_module

    class _TestJwksCache(JwksCache):
        async def get_keys(self) -> list[dict]:
            return _build_jwks()["keys"]

    identity_module.jwks_cache = _TestJwksCache()

    # Also patch settings so issuer/audience match the test tokens
    from apps.api import config as cfg_module
    original_settings = cfg_module.settings

    class _PatchedSettings:
        def __getattr__(self, name):
            return getattr(original_settings, name)

        @property
        def okta_issuer(self) -> str:
            return _ISSUER

        @property
        def okta_audience(self) -> str:
            return _AUDIENCE

    cfg_module.settings = _PatchedSettings()  # type: ignore[assignment]
    identity_module.settings = cfg_module.settings  # type: ignore[assignment]

    yield

    cfg_module.settings = original_settings
    identity_module.settings = original_settings


@pytest_asyncio.fixture(scope="session")
async def setup_tenants():
    """Ensure TENANT_A and TENANT_B rows exist in the tenants table (owner role)."""
    owner_url = TEST_DATABASE_URL.replace("://aura_app:aura_app@", "://aura_service:aura_service@", 1)
    owner_engine = create_async_engine(owner_url)
    async with owner_engine.begin() as conn:
        for tid in (TENANT_A, TENANT_B):
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, slug, display_name, okta_org_id) "
                    "VALUES (:id, :slug, :name, :okta_org_id) ON CONFLICT DO NOTHING"
                ),
                {"id": tid, "slug": str(tid), "name": str(tid), "okta_org_id": str(tid)},
            )
    await owner_engine.dispose()


@pytest_asyncio.fixture()
async def app_client(setup_tenants):
    from apps.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def get_session_for_tenant(tenant_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    async with TestAsyncSession() as session:
        async with session.begin():
            await set_tenant_rls(session, tenant_id)
            yield session


async def insert_test_user(*, tenant_id: UUID, okta_sub: str | None = None) -> User:
    """Insert a user directly via the owner connection (bypasses RLS)."""
    owner_url = TEST_DATABASE_URL.replace("://aura_app:aura_app@", "://aura_service:aura_service@", 1)
    owner_engine = create_async_engine(owner_url)
    now = datetime.now(UTC)
    user_id = uuid4()
    sub = okta_sub or f"okta|{uuid4().hex}"
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, okta_sub, email, roles, synced_at, created_at, updated_at) "
                "VALUES (:id, :tid, :sub, :email, '{}', :now, :now, :now) ON CONFLICT DO NOTHING"
            ),
            {"id": user_id, "tid": tenant_id, "sub": sub, "email": f"{sub}@example.com", "now": now},
        )
    await owner_engine.dispose()
    return User(id=user_id, tenant_id=tenant_id, okta_sub=sub, email=f"{sub}@example.com", roles=[], synced_at=now, created_at=now, updated_at=now)
