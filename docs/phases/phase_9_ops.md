# Fase 9 — Ops e Hardening
> AURA Backbone v4.3 · Fase 9 di 9
> **Prerequisito**: Fase 8 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/06_ops.md   (§22: jobs/retries; §23: observability; §24: degraded modes; §28: critical tests; §29: DoD)
docs/spec/02_services.md  (§14: prompt management fallback)
```

---

## Obiettivo

Langfuse integrato con fallback. OTel/LGTM con tutte le metriche obbligatorie. Tutti i degraded modes verificati. Critical failure tests passano. Sistema regge un load test a traffico moderato.

---

## Tasks obbligatori

### 9.1 — Langfuse integration
`aura/adapters/langfuse/client.py`:
- Inizializzare `Langfuse(secret_key=..., public_key=..., host=...)` all'avvio
- `get_prompt(prompt_id)` → string
- Fallback order esatto da `docs/spec/02_services.md §14.2`: Langfuse → file → errore esplicito
- Se Langfuse down: `logger.warning("langfuse_unavailable_using_fallback", ...)` + usa file
- File fallback in `registries/prompts/defaults/{prompt_id}.txt`

Creare almeno questi file fallback:
```
registries/prompts/defaults/
  platform_system_prompt.txt
  guardrail_policy_prompt.txt
```

### 9.2 — OTel setup
`aura/utils/observability.py`:
- `init_otel(service_name, otlp_endpoint)` da chiamare in `apps/api/main.py` e `apps/worker/main.py`
- Instrumentazione automatica FastAPI con `FastAPIInstrumentor`
- Instrumentazione SQLAlchemy con `SQLAlchemyInstrumentor`

### 9.3 — Metriche obbligatorie (§23.3)
Implementare tutte le metriche con `opentelemetry.metrics`:

| Metrica | Tipo | Label |
|---|---|---|
| `aura.request.latency_ms` | Histogram | `endpoint`, `method`, `status` |
| `aura.job.success_total` | Counter | `job_type`, `queue` |
| `aura.job.failure_total` | Counter | `job_type`, `queue` |
| `aura.retrieval.latency_ms` | Histogram | `space_id`, `reranker` |
| `aura.litellm.call_latency_ms` | Histogram | `model`, `tenant_id` |
| `aura.litellm.tokens_used` | Counter | `model`, `tenant_id`, `direction` |
| `aura.identity.sync_freshness_s` | Gauge | `tenant_id` |
| `aura.datasource.stale_count` | Gauge | `tenant_id` |
| `aura.pii.transform_error_total` | Counter | `mode`, `tenant_id` |
| `aura.sandbox.wall_time_s` | Histogram | `skill_name`, `status` |

### 9.4 — Degraded modes verificati (§24)
Per ogni degraded mode, verificare che il comportamento sia quello dichiarato:
- **Langfuse down**: API continua con fallback file
- **Qdrant down**: `/chat/respond` → HTTP 503 esplicito (no silent failure)
- **LiteLLM down**: model call → errore esplicito (no fallback implicito)
- **Secret store down**: connector sync non parte, `CredentialResolutionError`

### 9.5 — Retry e idempotency hardening
Verificare che tutti i job ARQ abbiano:
- `job_key` univoco e deterministico
- Lock Redis per risorse condivise
- Comportamento idempotente (stesso input → stesso output, nessun side effect doppio)

### 9.6 — Critical failure tests (§28.2)
Implementare ed eseguire tutti i 12 test obbligatori elencati in `docs/spec/06_ops.md §28.2`.
Questi test sono i gate finali: se anche uno solo fallisce, il sistema non è considerato production-ready.

### 9.7 — Load test baseline
Con `locust` o `k6`, verificare che il sistema regga traffico moderato:
- 50 utenti concorrenti
- Mix: 60% chat/respond, 30% retrieval, 10% agent runs
- P95 latency `/chat/respond` < 5000ms
- P95 latency `/chat/retrieve` < 500ms
- Zero errori 5xx su 1000 richieste

---

## Acceptance criteria (GATE — tutti i 12 critical failure tests)

```python
# tests/critical/test_critical_failures.py

async def test_1_tenant_isolation():
    """Utente tenant-A non vede dati tenant-B (DB + Qdrant)."""
    # ... (già verificato in Fase 1, ma ripetuto qui come regression guard)

async def test_2_stale_source_acl():
    """Documento con ACL revocata non appare in retrieval dopo re-sync."""
    # ... (già verificato in Fase 6)

async def test_3_stale_identity_mapping():
    """Utente rimosso dal gruppo non accede dopo sync."""
    await remove_user_from_group(USER_A, GROUP_X)
    await run_identity_sync(TENANT_A)
    # Re-index ACL
    await resync_datasource_acl(DATASOURCE_ID)
    token = generate_test_jwt(user_id=USER_A)
    results = await search_in_group_restricted_space(token)
    assert len(results) == 0

async def test_4_no_raw_pii_in_logs():
    """Con PiiPolicy attiva, nessun PII raw nei log."""
    # ... (già verificato in Fase 5)

async def test_5_retry_idempotency():
    """Job lanciato 2 volte produce lo stesso risultato."""
    doc_id = await upload_test_doc()
    v1 = await count_document_versions(doc_id)
    await trigger_ingest_job(doc_id)   # secondo run, stesso contenuto
    v2 = await count_document_versions(doc_id)
    assert v1 == v2

async def test_6_job_locks():
    """Due worker non processano lo stesso job contemporaneamente."""
    import asyncio
    results = await asyncio.gather(
        run_ingest_job_async(DOC_ID),
        run_ingest_job_async(DOC_ID),
    )
    # Solo uno dei due deve aver acquisito il lock e completato
    successes = sum(1 for r in results if r == "completed")
    assert successes == 1

async def test_7_runtime_artifact_immutability():
    """Tentativo di run su artifact non-published → 403."""
    draft = await upload_agent_only()
    r = await client.post(f"/api/v1/agents/{draft.name}/run", json={}, headers=auth(token))
    assert r.status_code == 403

async def test_8_trace_propagation():
    """trace_id presente in risposta API e nei log del worker."""
    r = await client.post("/api/v1/chat/respond", json={"message": "test", ...})
    trace_id = r.json()["trace_id"]
    # Cerca il trace_id nei log del worker (o nel tracing backend)
    assert await find_trace_in_worker_logs(trace_id)

async def test_9_fallback_prompt_correctness():
    """Langfuse down → fallback file usato correttamente."""
    with patch("aura.adapters.langfuse.client.get_prompt", side_effect=LangfuseUnavailableError()):
        r = await client.post("/api/v1/chat/respond", json={"message": "test", ...})
    assert r.status_code == 200  # non crasha

async def test_10_connector_temp_failure():
    """Sync fallisce e riprende con retry; indice precedente intatto."""
    initial_count = await count_indexed_chunks(SPACE_ID)
    with patch.object(SharePointConnector, "load_documents", side_effect=ConnectorUnavailableError()):
        await run_sync_job(DATASOURCE_ID)
    # Indice non deve essere stato cancellato
    assert await count_indexed_chunks(SPACE_ID) == initial_count

async def test_11_secret_never_serialized():
    """ResolvedCredentials non appare in nessun log o payload ARQ."""
    with capture_all_arq_payloads() as payloads:
        await trigger_connector_sync(DATASOURCE_ID)
    for p in payloads:
        assert "token_or_key" not in str(p)

async def test_12_sandbox_escape_prevention():
    """Skill che tenta network call → bloccata da SandboxPolicy."""
    # ... (già verificato in Fase 8)
```

---

## Note per Claude Code

- I critical failure tests NON sono opzionali. Sono il gate finale. Se uno fallisce, il sistema non è done.
- Per il load test, è accettabile usare dati sintetici e un LiteLLM mock che risponde in 100ms fissi. L'obiettivo è verificare la stabilità del sistema sotto carico, non la qualità delle risposte LLM.
- La metrica `aura.identity.sync_freshness_s` deve essere aggiornata dal cron job identity-sync, non calcolata on-demand nel health endpoint.
- Dopo questa fase: sistema production-ready per traffico moderato. Per scaling oltre (più tenant, più worker, K8s), aggiornare `infra/k8s/` e implementare `K8sJobSandboxProvider`.
