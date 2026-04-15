from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.config import settings
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.models import LocalAuthUser, Tenant, User
from aura.services.bootstrap import ensure_default_tenant
from aura.utils.passwords import hash_password
from tests.conftest import (
    TENANT_A,
    TENANT_B,
    TEST_DATABASE_URL,
    USER_A_SUB,
    USER_B_SUB,
    generate_test_jwt,
    get_session_for_tenant,
    insert_test_user,
)

pytestmark = pytest.mark.asyncio


async def test_valid_jwt_returns_me(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub=USER_A_SUB, email="user_a@example.com")
    r = await app_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["identity"]["tenant_id"] == str(TENANT_A)
    assert body["identity"]["okta_sub"] == USER_A_SUB


async def test_invalid_jwt_returns_401(app_client):
    r = await app_client.get("/api/v1/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert r.status_code == 401


async def test_expired_jwt_returns_401(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub=USER_A_SUB, expired=True)
    r = await app_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_missing_auth_returns_401(app_client):
    r = await app_client.get("/api/v1/me")
    assert r.status_code == 401


async def test_update_profile_updates_display_name(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|profile-user", email="profile@example.com")

    response = await app_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "Updated Profile Name"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Updated Profile Name"


async def test_local_user_can_change_password(app_client):
    tenant_id = UUID("aaaaaaaa-0000-0000-0000-0000000000aa")
    tenant_slug = f"local-password-{uuid4().hex[:8]}"
    admin_email = f"local-admin-{uuid4().hex[:8]}@example.com"
    owner_url = TEST_DATABASE_URL.replace("://aura_app:aura_app@", "://aura_service:aura_service@", 1)
    owner_engine = create_async_engine(owner_url)
    now = datetime.now(UTC)
    try:
        async with owner_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO tenants (id, slug, display_name, auth_mode, okta_org_id, status, created_at, updated_at)
                    VALUES (:id, :slug, :display_name, 'local', :okta_org_id, 'active', :now, :now)
                    ON CONFLICT (id) DO UPDATE
                    SET slug = :slug, display_name = :display_name, auth_mode = 'local', updated_at = :now
                    """
                ),
                {
                    "id": tenant_id,
                    "slug": tenant_slug,
                    "display_name": "Local Password Tenant",
                    "okta_org_id": str(tenant_id),
                    "now": now,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO local_auth_users (tenant_id, email, password_hash, display_name, roles, is_active, created_at, updated_at)
                    VALUES (:tenant_id, :email, :password_hash, :display_name, '{"admin","tenant_admin"}', TRUE, :now, :now)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "email": admin_email,
                    "password_hash": hash_password("old-password"),
                    "display_name": "Local Admin",
                    "now": now,
                },
            )

        login = await app_client.post(
            "/api/v1/auth/local/login",
            json={
                "tenant_slug": tenant_slug,
                "email": admin_email,
                "password": "old-password",
            },
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        change = await app_client.post(
            "/api/v1/auth/me/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "old-password", "new_password": "new-password-123"},
        )
        assert change.status_code == 204, change.text

        old_login = await app_client.post(
            "/api/v1/auth/local/login",
            json={
                "tenant_slug": tenant_slug,
                "email": admin_email,
                "password": "old-password",
            },
        )
        assert old_login.status_code == 401, old_login.text

        new_login = await app_client.post(
            "/api/v1/auth/local/login",
            json={
                "tenant_slug": tenant_slug,
                "email": admin_email,
                "password": "new-password-123",
            },
        )
        assert new_login.status_code == 200, new_login.text
    finally:
        await owner_engine.dispose()


async def test_provision_local_tenant_and_login(app_client):
    tenant_slug = f"local-test-{uuid4().hex[:8]}"
    provision = await app_client.post(
        "/api/v1/admin/tenants/provision",
        headers={"X-Bootstrap-Token": settings.bootstrap_token.get_secret_value()},
        json={
            "slug": tenant_slug,
            "display_name": "Local Test Tenant",
            "auth_mode": "local",
            "admin_email": "local-admin@example.com",
            "admin_password": "super-secret-password",
            "admin_display_name": "Local Admin",
        },
    )
    assert provision.status_code == 201, provision.text
    tenant_id = provision.json()["tenant_id"]

    login = await app_client.post(
        "/api/v1/auth/local/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "local-admin@example.com",
            "password": "super-secret-password",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await app_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["identity"]["tenant_id"] == tenant_id
    assert "tenant_admin" in body["identity"]["roles"]

    async with AsyncSessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
        assert tenant is not None
        assert tenant.auth_mode == "local"
        await set_tenant_rls(session, tenant_id)
        local_user = await session.scalar(select(LocalAuthUser).where(LocalAuthUser.tenant_id == tenant_id))
        assert local_user is not None
        assert local_user.password_hash != "super-secret-password"


async def test_public_tenant_catalog_exposes_active_tenants(app_client):
    tenant_slug = f"catalog-{uuid4().hex[:8]}"
    provision = await app_client.post(
        "/api/v1/admin/tenants/provision",
        headers={"X-Bootstrap-Token": settings.bootstrap_token.get_secret_value()},
        json={
            "slug": tenant_slug,
            "display_name": "Catalog Tenant",
            "auth_mode": "local",
            "admin_email": "catalog-admin@example.com",
            "admin_password": "catalog-password",
            "admin_display_name": "Catalog Admin",
        },
    )
    assert provision.status_code == 201, provision.text

    listing = await app_client.get("/api/v1/public/tenants")
    assert listing.status_code == 200, listing.text
    assert any(item["slug"] == tenant_slug and item["supports_password_login"] is True for item in listing.json())

    detail = await app_client.get(f"/api/v1/public/tenants/{tenant_slug}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["slug"] == tenant_slug
    assert detail.json()["auth_mode"] == "local"


async def test_default_tenant_bootstrap_creates_local_admin():
    tenant_slug = f"default-{uuid4().hex[:8]}"
    admin_email = f"bootstrap-{uuid4().hex[:8]}@example.com"

    old_enabled = settings.default_tenant_enabled
    old_slug = settings.default_tenant_slug
    old_display_name = settings.default_tenant_display_name
    old_auth_mode = settings.default_tenant_auth_mode
    old_admin_email = settings.default_tenant_admin_email
    old_admin_password = settings.default_tenant_admin_password
    old_admin_display_name = settings.default_tenant_admin_display_name

    settings.default_tenant_enabled = True
    settings.default_tenant_slug = tenant_slug
    settings.default_tenant_display_name = "Bootstrap Tenant"
    settings.default_tenant_auth_mode = "local"
    settings.default_tenant_admin_email = admin_email
    settings.default_tenant_admin_password = SecretStr("bootstrap-password")
    settings.default_tenant_admin_display_name = "Bootstrap Admin"
    try:
        await ensure_default_tenant()

        async with AsyncSessionLocal() as session:
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
            assert tenant is not None
            await set_tenant_rls(session, tenant.id)
            local_user = await session.scalar(
                select(LocalAuthUser).where(
                    LocalAuthUser.tenant_id == tenant.id,
                    LocalAuthUser.email == admin_email,
                )
            )
            assert local_user is not None
            assert "tenant_admin" in list(local_user.roles or [])
    finally:
        settings.default_tenant_enabled = old_enabled
        settings.default_tenant_slug = old_slug
        settings.default_tenant_display_name = old_display_name
        settings.default_tenant_auth_mode = old_auth_mode
        settings.default_tenant_admin_email = old_admin_email
        settings.default_tenant_admin_password = old_admin_password
        settings.default_tenant_admin_display_name = old_admin_display_name


async def test_platform_admin_can_provision_tenant_without_bootstrap_token(app_client):
    tenant_slug = f"default-{uuid4().hex[:8]}"
    admin_email = f"platform-{uuid4().hex[:8]}@example.com"

    old_enabled = settings.default_tenant_enabled
    old_slug = settings.default_tenant_slug
    old_display_name = settings.default_tenant_display_name
    old_auth_mode = settings.default_tenant_auth_mode
    old_admin_email = settings.default_tenant_admin_email
    old_admin_password = settings.default_tenant_admin_password
    old_admin_display_name = settings.default_tenant_admin_display_name

    settings.default_tenant_enabled = True
    settings.default_tenant_slug = tenant_slug
    settings.default_tenant_display_name = "DEFAULT"
    settings.default_tenant_auth_mode = "local"
    settings.default_tenant_admin_email = admin_email
    settings.default_tenant_admin_password = SecretStr("platform-password")
    settings.default_tenant_admin_display_name = "Platform Admin"
    try:
        await ensure_default_tenant()

        login = await app_client.post(
            "/api/v1/auth/local/login",
            json={
                "tenant_slug": tenant_slug,
                "email": admin_email,
                "password": "platform-password",
            },
        )
        assert login.status_code == 200, login.text

        provision = await app_client.post(
            "/api/v1/admin/tenants/provision",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            json={
                "slug": f"child-{uuid4().hex[:8]}",
                "display_name": "Child Tenant",
                "auth_mode": "local",
                "admin_email": "child-admin@example.com",
                "admin_password": "child-password",
                "admin_display_name": "Child Admin",
            },
        )
        assert provision.status_code == 201, provision.text
    finally:
        settings.default_tenant_enabled = old_enabled
        settings.default_tenant_slug = old_slug
        settings.default_tenant_display_name = old_display_name
        settings.default_tenant_auth_mode = old_auth_mode
        settings.default_tenant_admin_email = old_admin_email
        settings.default_tenant_admin_password = old_admin_password
        settings.default_tenant_admin_display_name = old_admin_display_name


async def test_local_tenant_admin_can_manage_users_and_auth_mode(app_client):
    tenant_slug = f"admin-local-{uuid4().hex[:8]}"
    okta_org_id = f"test-org-{uuid4().hex[:8]}"
    provision = await app_client.post(
        "/api/v1/admin/tenants/provision",
        headers={"X-Bootstrap-Token": settings.bootstrap_token.get_secret_value()},
        json={
            "slug": tenant_slug,
            "display_name": "Admin Local Tenant",
            "auth_mode": "local",
            "admin_email": "tenant-admin@example.com",
            "admin_password": "super-secret-password",
            "admin_display_name": "Tenant Admin",
        },
    )
    assert provision.status_code == 201, provision.text

    login = await app_client.post(
        "/api/v1/auth/local/login",
        json={
            "tenant_slug": tenant_slug,
            "email": "tenant-admin@example.com",
            "password": "super-secret-password",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    current = await app_client.get("/api/v1/admin/tenants/current", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["auth_mode"] == "local"

    create_user = await app_client.post(
        "/api/v1/admin/tenants/local-users",
        headers=headers,
        json={
            "email": "analyst@example.com",
            "password": "analyst-password",
            "display_name": "Analyst",
            "roles": ["user"],
        },
    )
    assert create_user.status_code == 201, create_user.text
    created_user = create_user.json()
    assert created_user["email"] == "analyst@example.com"

    list_users = await app_client.get("/api/v1/admin/tenants/local-users", headers=headers)
    assert list_users.status_code == 200, list_users.text
    assert len(list_users.json()) == 2

    update_user = await app_client.patch(
        f"/api/v1/admin/tenants/local-users/{created_user['id']}",
        headers=headers,
        json={"roles": ["user", "reviewer"], "is_active": False},
    )
    assert update_user.status_code == 200, update_user.text
    assert update_user.json()["is_active"] is False
    assert "reviewer" in update_user.json()["roles"]

    runtime_key = await app_client.get("/api/v1/admin/llm/runtime-key", headers=headers)
    assert runtime_key.status_code == 200, runtime_key.text
    assert runtime_key.json()["synced"] is False
    assert runtime_key.json()["sync_mode"] == "master-key-fallback"

    switch_okta = await app_client.patch(
        "/api/v1/admin/tenants/current/auth",
        headers=headers,
        json={
            "auth_mode": "okta",
            "okta_org_id": okta_org_id,
            "okta_jwks_url": "https://test.okta.example.com/v1/keys",
            "okta_issuer": "https://test.okta.example.com",
            "okta_audience": "api://default",
        },
    )
    assert switch_okta.status_code == 200, switch_okta.text
    assert switch_okta.json()["auth_mode"] == "okta"


async def test_non_admin_cannot_access_admin_api_keys(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|plain-user", email="plain-user@example.com")

    response = await app_client.get("/api/v1/admin/api-keys", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403, response.text


async def test_non_admin_cannot_access_admin_agents(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|plain-agent-user", email="plain-agent-user@example.com")

    response = await app_client.get("/api/v1/admin/agents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403, response.text


async def test_cross_tenant_isolation(setup_tenants):
    """CRITICAL: utente tenant-A non vede record di tenant-B nel DB."""
    # Inserisci un utente direttamente in TENANT_B (bypassa RLS con owner role)
    await insert_test_user(tenant_id=TENANT_B, okta_sub=USER_B_SUB)

    # Utente TENANT_A apre una sessione con RLS impostato su TENANT_A
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, TENANT_A)
            result = await session.execute(select(User))
            users = result.scalars().all()

    assert all(u.tenant_id == TENANT_A for u in users), (
        f"VIOLAZIONE TENANCY: utente vede dati di altro tenant. "
        f"tenant_ids trovati: {sorted({str(u.tenant_id) for u in users})}"
    )


async def test_rls_resets_after_request(setup_tenants):
    """SET LOCAL deve resettarsi a fine transazione."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, TENANT_A)
            # dentro la transazione il setting è attivo
            val_inside = await session.scalar(
                text("SELECT current_setting('app.current_tenant_id', true)")
            )
        assert val_inside == str(TENANT_A)

        # fuori dalla transazione (SET LOCAL scaduto), deve essere vuoto o stringa vuota
        val_outside = await session.scalar(
            text("SELECT current_setting('app.current_tenant_id', true)")
        )
    assert val_outside in ("", None, "00000000-0000-0000-0000-000000000000"), (
        f"RLS NON resettato dopo la transazione: valore rimasto '{val_outside}'"
    )
