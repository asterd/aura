from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.models import User
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
