from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from apps.api.config import settings
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.models import LocalAuthUser, Tenant, User
from tests.conftest import (
    TENANT_A,
    TENANT_B,
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
    assert val_outside in ("", None), (
        f"RLS NON resettato dopo la transazione: valore rimasto '{val_outside}'"
    )
