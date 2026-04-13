# Fase 1 — Identity
> AURA Backbone v4.3 · Fase 1 di 9
> **Prerequisito**: Fase 0 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.1: UserIdentity, RequestContext)
docs/spec/02_services.md    (§9: Identity model, §10: RLS lifecycle)
docs/spec/07_db_schema.md   (§31.1: tabelle users, groups, memberships)
```

---

## Obiettivo

JWT validato → `UserIdentity` → `RequestContext` → RLS impostato → `/me` risponde correttamente. Tenancy isolation testata e verde.

---

## Tasks obbligatori

### 1.1 — Migration tabelle identity
Da `docs/spec/07_db_schema.md §31.1`: tabelle `users`, `groups`, `user_group_memberships`.
Abilitare RLS su tutte e tre con `FORCE ROW LEVEL SECURITY`.
Policy SQL pattern: `tenant_id = current_setting('app.current_tenant_id')::UUID`.

### 1.2 — JWT validation middleware
- Fetch JWKS da `settings.OKTA_JWKS_URL` con caching (TTL 1h)
- Validare `iss`, `aud`, `exp`
- Estrarre `sub` (okta_sub), `email`, `groups`, `roles` dai claims
- Se token non valido: HTTP 401

### 1.3 — UserIdentity e RequestContext
Costruire dai claims JWT i modelli esatti da `docs/spec/01_contracts.md §8.1`.
- `user_id`: UUID del record users (upsert on first login)
- `group_ids`: UUIDs dei gruppi AURA (mappati da okta group names)
- `request_id`: `uuid4()` per ogni request
- `trace_id`: da header `X-Trace-Id` o generato

### 1.4 — DB session dependency con RLS
```python
# apps/api/dependencies/db.py
async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    identity: UserIdentity = request.state.identity
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, identity.tenant_id)
            request.state.db = session
            yield session
```

### 1.5 — `/me` endpoint
`GET /api/v1/me` → `MeResponse` (da `docs/spec/05_api.md §21.8`).
Richiede auth. Legge il record `users` della session corrente.

### 1.6 — `/health` aggiornato
Aggiungere check Okta JWKS raggiungibile.

---

## Acceptance criteria (GATE)

```python
# tests/integration/test_identity.py

async def test_valid_jwt_returns_me():
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    r = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["identity"]["tenant_id"] == str(TENANT_A)

async def test_invalid_jwt_returns_401():
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401

async def test_cross_tenant_isolation():
    """CRITICAL: utente tenant-A non vede record tenant-B nel DB."""
    token_a = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    token_b = generate_test_jwt(tenant_id=TENANT_B, user_id=USER_B)

    # Inserisci un record in TENANT_B
    await insert_test_user(tenant_id=TENANT_B)

    # Utente TENANT_A non deve vederlo
    async with get_session_for_token(token_a) as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert all(u.tenant_id == TENANT_A for u in users), \
            "VIOLAZIONE TENANCY: utente vede dati di altro tenant"

async def test_rls_resets_after_request():
    """SET LOCAL deve resettarsi a fine transazione."""
    token = generate_test_jwt(tenant_id=TENANT_A)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, TENANT_A)
        # Fuori dalla transazione, il setting deve essere vuoto
        val = await session.scalar(text("SELECT current_setting('app.current_tenant_id', true)"))
        assert val == '' or val is None
```

---

## Note per Claude Code

- Usare `python-jose` o `PyJWT` per la validazione JWT, non implementare crypto custom.
- Il mapping okta_group_name → AURA group UUID avviene nella tabella `groups`. Se un gruppo Okta non è ancora mappato, `group_ids` è una lista vuota (non errore).
- Non implementare ancora autorizzazione granulare su risorse — solo autenticazione e tenancy in questa fase.
- `generate_test_jwt` è un helper di test che genera token firmati con chiave locale per i test. Non usare token reali Okta nei test automatici.
