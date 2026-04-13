# AURA — Guida operativa per Claude Code
> Versione spec: 4.3 · Aprile 2026
> Leggere QUESTO file all'inizio di ogni sessione.

---

## Source of truth

La specifica è suddivisa in moduli in `docs/spec/`. Non caricare l'intera specifica in una sessione.
Per ogni fase, leggere SOLO i file elencati nella sezione "File da leggere" del file di fase.

| File | Contenuto |
|---|---|
| `docs/spec/00_core.md` | Regole operative, stack approvato, decisioni architetturali (§1-6) |
| `docs/spec/01_contracts.md` | Tutti i contratti Pydantic — NON modificare mai (§8) |
| `docs/spec/02_services.md` | Service boundaries, identity, RLS, prompt, chat, PII (§7,9,10,13-16) |
| `docs/spec/03_knowledge.md` | KnowledgeSpace, document lifecycle, Qdrant payload (§11-12) |
| `docs/spec/04_agents.md` | Agent runtime, registry, sandbox, connectors (§17-20) |
| `docs/spec/05_api.md` | API surface e schemas pubblici (§21) |
| `docs/spec/06_ops.md` | Jobs, observability, degraded modes, anti-pattern, DoD (§22-29) |
| `docs/spec/07_db_schema.md` | Schema DB completo, RLS SQL, ruoli (§31) |
| `docs/spec/08_ux_architecture.md` | UX: threading, streaming, composer, sidebar, artifact viewer, AgentChatService (§35) |
| `docs/spec/09_triggered_agents.md` | Triggered & autonomous agents, cron/event triggers, webhook inbound (§36) |
| `docs/spec/10_mcp_bridge.md` | MCP Bridge: AURA come MCP Server + skill mcp_client outbound (§37) |
| `docs/spec/11_agent_chat_integration.md` | Agent-in-chat: @mention, AgentChatService, streaming eventi agente (§38) |

---

## Regole operative VINCOLANTI (§1)

1. **Un task alla volta** — un bounded context per task.
2. **Un bounded context per task** — non toccare più servizi insieme.
3. **Thin router, heavy service** — zero business logic nei router.
4. **Framework-first, custom-last** — usa le librerie approvate prima di scrivere custom.
5. **I service methods ricevono dipendenze già risolte** — session, context, policy sempre iniettati.
6. **Nessuna business logic nei router, model layer o adapter.**
7. **No shared state in-memory tra processi.**
8. **Ogni task deve avere verifica automatizzabile.**
9. **Ogni placeholder esplicito**: `raise NotImplementedError("reason")` — mai `pass`.

---

## Stack approvato (§3) — versioni vincolanti

```
Python          3.12.x
FastAPI         0.115.x
SQLAlchemy      2.0.x     (async engine obbligatorio)
Alembic         1.13.x
asyncpg         0.29.x
ARQ             0.25.x
Qdrant client   1.9.x
llama-index-core 0.10.x  (NON il meta-package llama-index)
pydantic-ai     ~=1.79   (serie 1.x stabile, V1 API commitment)
LiteLLM Proxy   1.40.x   (≥4 CPU core, ≥8 GB RAM in prod)
Langfuse SDK    3.x
Presidio        2.2.x
```

---

## Anti-pattern VIETATI (§25) — Claude Code MUST NOT

- ❌ Business logic nei router
- ❌ Qdrant diretto dal layer HTTP (sempre via RetrievalService)
- ❌ `AsyncSession` creata nei service methods (sempre iniettata)
- ❌ Policy hardcoded nei prompt agentici
- ❌ Skill eseguite dentro il processo API
- ❌ Agenti eseguiti da artifact non `published`
- ❌ Raw PII in log/traces se policy non lo consente
- ❌ `exec()` o `eval()` nel RuntimeLoader
- ❌ `ResolvedCredentials` serializzate in qualsiasi forma persistente
- ❌ Meta-package `llama-index` (usare solo sotto-package)
- ❌ Agno, LangChain, LangGraph, Celery — verificare con `pip show` prima di ogni sessione

---

## Contratti — SEMPRE da `aura/domain/contracts.py`

I seguenti modelli NON devono essere ridefiniti inline. Importarli sempre:

```python
from aura.domain.contracts import (
    UserIdentity, RequestContext,
    RetrievalRequest, RetrievalResult, Citation,
    ChatRequest, ChatResponse, ChatStreamEvent,
    AgentDeps, AgentRunRequest, AgentRunResult,
    ModelPolicy, PiiPolicy, SandboxPolicy,
    RetrievalProfile, EmbeddingProfile, ToneProfile,
    ConnectorCredentials, ResolvedCredentials,
    SandboxInput, SandboxResult,
    JobPayload,
)
```

---

## Session lifecycle — pattern obbligatorio (§10)

```python
# In ogni FastAPI dependency che apre una session:
async with AsyncSessionLocal() as session:
    async with session.begin():
        await set_tenant_rls(session, tenant_id)
        # passa session ai service — mai crearla nei service
        result = await some_service.do_something(session=session, ...)
    return result
```

Il ruolo DB runtime è `aura_app` (non `postgres`, non il table owner). Vedere `docs/spec/07_db_schema.md §31.7`.

---

## Sequenza implementazione OBBLIGATORIA (§27)

```
Fase 0 → Foundation        (infra, settings, health, ARQ skeleton)
Fase 1 → Identity          (JWT, UserIdentity, RLS, /me)
Fase 2 → Spaces            (CRUD spaces, ACL, memberships)
Fase 3 → Upload+Ingestion  (S3, LlamaIndex, Qdrant upsert)
Fase 4 → Retrieval+Chat    (RetrievalService, ChatService, SSE)
Fase 5 → Policies+PII      (ModelPolicy, PiiPolicy, Presidio)
Fase 6 → Connectors        (ConnectorWrapper, SecretStore, identity sync)
Fase 7 → Agent Registry    (manifest, RegistryService, RuntimeLoader, AgentService)
Fase 8 → Skills+Sandbox    (SandboxProvider, Docker, K8s)
Fase 9 → Ops+Hardening     (Langfuse, OTel, degraded modes, load test)
```

**REGOLA**: non iniziare la Fase N+1 prima che i test della Fase N siano verdi.

---

## Definition of Done (§29)

Una feature è DONE solo se:
- ✅ Rispetta i contratti di `docs/spec/01_contracts.md`
- ✅ Ha test o verifica ripetibile
- ✅ Non viola tenancy o PII
- ✅ È osservabile (metriche e log minimi)
- ✅ Non introduce anti-pattern (§25)
- ✅ Non introduce dipendenze non approvate (§3)
- ✅ Ha comportamento degradato definito se necessario

---

## PydanticAI agent — pattern obbligatorio (§17.5)

Ogni `agent.py` in un package AURA DEVE esporre:

```python
def build(deps: AgentDeps) -> Agent[AgentDeps]:
    ...
```

I tool DEVONO verificare `ctx.deps.allowed_spaces` e `ctx.deps.allowed_tools`.
I tool NON DEVONO importare ORM, SessionFactory o config globale.
