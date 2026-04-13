# Fase 7 — Agent Registry
> AURA Backbone v4.3 · Fase 7 di 9
> **Prerequisito**: Fase 6 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.5: AgentDeps, AgentRunRequest, AgentRunResult)
docs/spec/04_agents.md      (§17: agent backbone; §18: registry e publish flow; §19.5: RuntimeLoader)
docs/spec/07_db_schema.md   (§31.4: agent_packages, agent_versions, agent_runs)
docs/spec/06_ops.md         (§22.4: retry policy agent-run)
```

⚠️ Prima di iniziare: verificare `pydantic-ai~=1.79` installato. Vedere pattern obbligatorio in CLAUDE.md.

---

## Obiettivo

Upload e publish di un agent package. `AgentService.run_agent` funzionante. Agent eseguito solo se `published`. PII rispettato nell'input/output. Agent-as-tool per orchestrator.

---

## Tasks obbligatori

### 7.1 — Migration tabelle
Da `docs/spec/07_db_schema.md §31.4`: `agent_packages`, `agent_versions`, `agent_runs`.
`agent_versions.status` CHECK constraint obbligatorio.

### 7.2 — Manifest validation
`aura/adapters/registry/manifest_validator.py`:
- Parsing YAML → dizionario
- Validazione schema obbligatorio (kind, name, version, agent_type, runtime, entrypoint, allowed_tools, allowed_spaces, model_policy, timeout_s, status)
- Se `status == "published"` nel manifest ma smoke test non è passato: reject
- Restituire errori strutturati, non eccezioni generiche

### 7.3 — RegistryService
`aura/services/registry_service.py`:
```python
async def upload_and_validate(session, zip_bytes, manifest_yaml, uploaded_by) -> AgentVersion
async def publish(session, agent_version_id, published_by) -> AgentVersion
async def resolve_agent_version(session, agent_name, requested_version) -> AgentVersion
async def get_runtime_artifact_ref(session, version) -> str  # S3 key
```
Il `publish` fallisce se `version.status != "validated"`.
L'artifact è caricato su S3 con SHA256 verificato prima del record DB.

### 7.4 — RuntimeLoader
`aura/adapters/runtime/loader.py` — implementare il contratto da `docs/spec/04_agents.md §19.5`:
- Download artifact da S3 in `tempfile.mkdtemp()`
- Verifica SHA256 contro `agent_versions.artifact_sha256`
- Estrai zip
- Usa `importlib.util.spec_from_file_location` + `importlib.util.module_from_spec`
- Estrai funzione `build` per nome
- Verifica signature
- Pulisci temp dir in `finally`

**MUST NOT**: `exec()`, `eval()`, import globali del codice agente.

### 7.5 — AgentService
`aura/services/agent_service.py` — implementare il pseudocodice normativo da `docs/spec/04_agents.md §17.3` **esattamente**:
1. Resolve published version (errore se non published)
2. Authorize user
3. Resolve ModelPolicy, PiiPolicy, system prompt
4. Build AgentDeps
5. Load build_fn via RuntimeLoader
6. Transform input (PII)
7. `agent = build_fn(deps)` → `raw_result = await agent.run(...)`
8. Transform output (PII)
9. Persist AgentRun
10. Emit audit

### 7.6 — Agent APIs
```
POST /api/v1/agents/{name}/run          → AgentRunApiResponse
POST /api/v1/admin/agents/upload        → AgentUploadResponse (multipart)
POST /api/v1/admin/agents/{id}/publish  → AgentVersion
GET  /api/v1/admin/agents               → list[AgentVersion]
```

### 7.7 — Agent-as-tool (orchestrator)
Per agent con `agent_type = "orchestrator"`, implementare il tool `agent.delegate`:
```python
@agent.tool
async def delegate_to_agent(ctx, agent_name: str, input_data: dict) -> dict:
    if agent_name not in ctx.deps.allowed_tools:
        raise PermissionError(...)
    return await agent_service.run_agent(agent_name=agent_name, input=input_data, ...)
```

---

## Acceptance criteria (GATE)

```python
async def test_non_published_agent_not_executable():
    """Un agent in stato draft non può essere eseguito."""
    draft_version = await upload_agent_package(status="draft")
    r = await client.post(f"/api/v1/agents/{draft_version.name}/run",
        json={"input": {}}, headers=auth(admin_token))
    assert r.status_code == 403

async def test_agent_run_e2e():
    """Upload → publish → run → result persisted."""
    # Crea e pubblica un agent minimale conforme al pattern §17.5
    version = await upload_and_publish_test_agent()

    r = await client.post(f"/api/v1/agents/{version.name}/run",
        json={"input": {"query": "test"}}, headers=auth(user_token))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["trace_id"]

    # Verifica persistenza
    run = await get_agent_run(body["run_id"])
    assert run.status == "succeeded"

async def test_pii_respected_in_agent_io():
    """Con PiiPolicy attiva, input/output agent devono essere trasformati."""
    version = await upload_and_publish_pii_test_agent()
    # L'agent fa echo dell'input
    r = await client.post(f"/api/v1/agents/{version.name}/run",
        json={"input": {"text": "CF: RSSMRA85M01H501Z"}},
        headers=auth(user_with_pii_policy_token))
    body = r.json()
    # L'output non deve contenere il CF raw
    assert "RSSMRA85M01H501Z" not in str(body.get("output_text", ""))

async def test_artifact_sha256_verified():
    """Se l'artifact S3 è corrotto (SHA mismatch), il run deve fallire esplicitamente."""
    version = await upload_and_publish_test_agent()
    await corrupt_s3_artifact(version.artifact_ref)
    r = await client.post(f"/api/v1/agents/{version.name}/run",
        json={"input": {}}, headers=auth(user_token))
    assert r.status_code in (400, 500)
    assert "sha256" in r.json().get("detail", "").lower()

async def test_tool_not_in_allowed_tools_blocked():
    """Tool non dichiarato nel manifest deve essere bloccato da AgentService."""
    # L'agent tenta di chiamare un tool non in allowed_tools
    result = await run_agent_with_unauthorized_tool()
    assert result.status == "failed"
    assert "PermissionError" in result.error_message
```

---

## Note per Claude Code

- L'agent minimale di test da usare negli acceptance test deve seguire ESATTAMENTE il pattern di CLAUDE.md (§17.5). Non inventare pattern diversi.
- `allowed_tools` nel manifest sono stringhe come `"knowledge.search"`, `"file.read"`, `"agent.delegate"`. `AgentService` verifica che i tool registrati nell'agent siano un sottoinsieme di questa lista prima del run.
- `agent_runs` ha `retry policy: max 1` — gli agent run non si ritentano automaticamente per evitare side effects doppi. Se un run fallisce, l'utente deve rilanciarlo esplicitamente.
- Il `smoke_test` del manifest (se presente) viene eseguito durante `upload_and_validate`, non durante il run. In questa fase può essere uno stub che verifica solo che `build` sia importabile.
