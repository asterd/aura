# Fase 6 — Connectors Enterprise
> AURA Backbone v4.3 · Fase 6 di 9
> **Prerequisito**: Fase 5 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.4: NormalizedACL, LoadedDocument; §8.12: ConnectorCredentials, ResolvedCredentials)
docs/spec/04_agents.md      (§20: Connector model, failure behavior, credential resolution)
docs/spec/07_db_schema.md   (§31.2: datasources con credentials_ref)
docs/spec/06_ops.md         (§22: retry policy connector-sync)
```

---

## Obiettivo

`ConnectorWrapper` Protocol implementato. Un connector enterprise (SharePoint o Google Drive) funzionante con ACL normalization. Identity sync job (Okta → DB). Datasource marcato `stale` se sync non avviene entro soglia.

---

## Tasks obbligatori

### 6.1 — SecretStore abstraction
`aura/utils/secrets.py`:
```python
class SecretStore(Protocol):
    async def get(self, ref: str) -> str: ...
    async def put(self, ref: str, value: str) -> None: ...
```
Implementazioni:
- `EnvSecretStore` (dev locale: legge da env vars)
- `VaultSecretStore` (prod: stub con `raise NotImplementedError`)

**REGOLA**: `ResolvedCredentials` viene creato in-memory e NON viene mai passato come payload ARQ. Il job riceve solo `secret_ref` e risolve autonomamente all'avvio.

### 6.2 — ConnectorWrapper Protocol
`aura/adapters/connectors/base.py` — implementare il contratto esatto da `docs/spec/04_agents.md §20.1`.
Signature `load_documents` riceve `ResolvedCredentials`, non `dict`.

### 6.3 — Primo connector (scegliere uno)
**Opzione A — SharePoint** (`aura/adapters/connectors/sharepoint.py`):
- `connector_type = "sharepoint"`
- `supports_access_control = True`
- `supports_incremental_sync = True`
- `load_documents`: Microsoft Graph API, delta query per incrementale
- ACL normalization: Groups Entra → `NormalizedACL.allow_groups` (UUIDs AURA)

**Opzione B — Google Drive** (`aura/adapters/connectors/gdrive.py`):
- `connector_type = "gdrive"`
- `supports_access_control = True`
- ACL normalization: Google Groups → `NormalizedACL.allow_groups`

Implementare il failure behavior da `docs/spec/04_agents.md §20.2` (tabella con 4 scenari).

### 6.4 — Connector sync job
`apps/worker/jobs/ingestion.py` — `connector_sync_job(ctx, payload)`:
1. Risolvi `ResolvedCredentials` dal `secret_ref` del datasource
2. Iterate `connector.load_documents(datasource_id, credentials, cursor)`
3. Per ogni `LoadedDocument`: enqueue `ingest_document_job`
4. Per documenti `is_deleted=True`: mark document `deleted` nel DB e rimuovi chunks da Qdrant
5. Aggiorna `datasource.sync_cursor` e `last_sync_at`
6. Se fallisce: mark `last_sync_status = "failed"` o `"auth_error"`

**Job key**: `sync:{datasource_id}`
**Retry**: max 3, backoff 120s
**Stale threshold**: se `now - last_sync_at > datasource.stale_threshold_s`, mark `stale`

### 6.5 — Identity sync job
`apps/worker/jobs/identity_sync.py` — `identity_sync_job(ctx, payload)`:
1. Fetch users e groups da Okta Management API
2. Upsert `users` e `groups` nel DB (per il tenant)
3. Upsert `user_group_memberships`
4. Non cancellare mapping in modo distruttivo — mark `stale` se non visti
5. Restituire `IdentitySyncResult`

**Cron**: ogni ora per tenant attivi
**Freshness metric**: `aura.identity.sync_freshness_s = now - last_sync_at`

### 6.6 — Stale datasource monitoring
`GET /api/v1/health` aggiornato con `aura.datasource.stale_count` per il tenant corrente.

---

## Acceptance criteria (GATE)

```python
async def test_credentials_never_serialized():
    """ResolvedCredentials non deve apparire in nessun payload ARQ."""
    import json
    payloads_enqueued = []
    # Mock ARQ enqueue per catturare i payload
    with patch("arq.ArqRedis.enqueue_job") as mock_enqueue:
        await trigger_connector_sync(DATASOURCE_ID)
        for call in mock_enqueue.call_args_list:
            payload_str = json.dumps(call.args)
            assert "token_or_key" not in payload_str, "ResolvedCredentials nel payload ARQ!"
            assert "client_secret" not in payload_str.lower()

async def test_acl_normalization():
    """ACL del connector devono essere normalizzate a NormalizedACL con UUIDs AURA."""
    raw_acl = {"allow": ["group:hr-team@company.com"]}
    connector = SharePointConnector()
    normalized = connector.normalize_acl(raw_acl, tenant_id=TENANT_A)
    assert isinstance(normalized, NormalizedACL)
    assert len(normalized.allow_groups) > 0
    assert all(isinstance(g, UUID) for g in normalized.allow_groups)

async def test_stale_acl_after_sync():
    """Documento con ACL revocata non deve apparire nel retrieval dopo re-sync."""
    # Doc indicizzato con accesso per USER_A
    await index_doc_with_acl(allow_users=[USER_A_OKTA_SUB])
    token = generate_test_jwt(user_id=USER_A)
    r = await search(token, "test")
    assert len(r["citations"]) > 0   # USER_A vede il doc

    # Revocare accesso e re-sync
    await revoke_acl_and_resync()
    r = await search(token, "test")
    assert len(r["citations"]) == 0  # USER_A non vede più il doc

async def test_connector_auth_failure_marks_datasource():
    """Se le credenziali scadono, il datasource deve essere marcato auth_error."""
    with patch.object(SharePointConnector, "load_documents", side_effect=ConnectorAuthError()):
        await run_sync_job(DATASOURCE_ID)
    ds = await get_datasource(DATASOURCE_ID)
    assert ds.last_sync_status == "auth_error"

async def test_identity_sync_result():
    result = await run_identity_sync(TENANT_A)
    assert isinstance(result, IdentitySyncResult)
    assert result.completed_at is not None
    assert result.partial_failures == 0
```

---

## Note per Claude Code

- Il job ARQ riceve `datasource_id` e `secret_ref`, NON le credenziali risolte. La resoluzione avviene nel job stesso all'avvio, non prima dell'enqueue.
- Per dev locale senza Okta/SharePoint reali, implementare stub `MockConnector` e `MockSecretStore` usabili nei test.
- `NormalizedACL.allow_groups` contiene UUID AURA interni — non i group IDs di Okta o Microsoft. La mappatura avviene tramite la tabella `groups`.
- La metric `aura.datasource.stale_count` deve essere emessa come gauge OTel, non solo calcolata on-demand.
