# AURA Spec — §22-29: Jobs, Observability, Degraded Modes, Anti-patterns, DoD
> Source: AURA Backbone v4.3

## 22. Jobs, retries e idempotenza

### 22.1 Regole generali

Ogni job MUST:

- avere `job_key`
- essere idempotente
- gestire retry espliciti con backoff esponenziale
- usare lock distribuito Redis se tocca risorse condivise
- persistere stato finale

### 22.2 Esempio job key

- `sync:{datasource_id}`
- `ingest:{document_id}:{version_hash}`
- `agent-run:{run_id}`
- `identity-sync:{tenant_id}:{hour_bucket}`

### 22.3 ARQ rules

- workload lunghi fuori dall'API
- cron jobs solo dove appropriato
- job timeout espliciti
- graceful shutdown configurato
- dead letter: job falliti > N volte vengono marcati `dead` in DB e generano alert

### 22.4 Retry policy standard

| Job type | max_retries | backoff |
|---|---|---|
| ingestion | 3 | exponential 30s base |
| agent-run | 1 | no retry (side effects) |
| identity-sync | 5 | exponential 60s base |
| connector-sync | 3 | exponential 120s base |

---

## 23. Observability

### 23.1 Ownership

**Langfuse**:
- prompt management
- model-call traces prodotto
- agent/chat traces di alto livello
- token usage per tenant

**OTel / LGTM**:
- request latency per endpoint
- DB/Redis/Qdrant timings
- worker jobs success/failure
- structured logs
- operational traces

### 23.2 Regole

- trace id propagato tra API e worker via `JobPayload.trace_id`
- raw PII vietata nei traces dove `pii_policy.allow_raw_in_traces = False`
- niente doppio tracing della stessa operazione logica

### 23.3 Metriche minime obbligatorie

- `aura.request.latency_ms` per endpoint
- `aura.job.success_total` / `aura.job.failure_total` per queue
- `aura.retrieval.latency_ms`
- `aura.litellm.call_latency_ms`
- `aura.litellm.tokens_used` per tenant
- `aura.cost.estimated_usd`
- `aura.cost.budget_block_total`
- `aura.identity.sync_freshness_s` per tenant
- `aura.datasource.stale_count`
- `aura.pii.transform_error_total`
- `aura.sandbox.wall_time_s`

---

## 24. Degraded modes

### 24.1 Langfuse down
- usare fallback file bundled
- log WARNING con trace_id
- continuare a servire richieste

### 24.2 Qdrant down
- retrieval fallisce esplicitamente con HTTP 503
- chat knowledge-based non simula successo

### 24.3 LiteLLM down
- model call fallisce esplicitamente
- nessun fallback implicito a provider diretto

### 24.4 Connector down
- sync fallisce dopo retry
- ultimo indice valido resta disponibile
- datasource marcato `stale` se oltre soglia configurabile

### 24.5 Sandbox down
- skill run fallisce con errore strutturato
- errore tool strutturato lato agente orchestrator

### 24.6 Identity sync down
- ultimo mapping valido noto resta attivo
- freshness scade e viene esposta su `/health` e metriche
- alerting operativo via OTel

### 24.7 Secret store down
- connector sync non parte (no credential resolution)
- errore esplicito: `CredentialResolutionError`
- nessun fallback a credenziali cacheate

### 24.8 Budget hard limit exceeded
- model call bloccata con errore esplicito
- nessun tentativo verso LiteLLM
- evento audit e metrica `aura.cost.budget_block_total`

## 24B. Cost governance

Regole obbligatorie:

- il controllo budget avviene prima della model call
- il recording usage avviene dopo la model call con migliore stima disponibile
- per streaming, il costo può essere finalizzato a fine stream
- se il costo reale non è disponibile, usare una stima deterministica documentata
- i gate hard limit sono fail-closed

---

## 25. Anti-patterns

Questa sezione è vincolante. Il coding agent MUST NOT:

1. mettere business logic nei router
2. interrogare Qdrant direttamente dal layer HTTP
3. creare `AsyncSession` nei service methods
4. hardcodare policy nei prompt agentici
5. eseguire skill dentro il processo API
6. eseguire agenti da artifact non `published`
7. salvare raw PII nei log se policy non lo consente
8. bypassare il retrieval filter builder
9. permettere a un tool agentico accesso ORM diretto
10. usare fallback silenziosi non auditati
11. mutare artifact `published`
12. costruire modelli Pydantic ad hoc scollegati dai contratti centrali
13. serializzare `ResolvedCredentials` in qualsiasi forma persistente
14. usare `exec()` o `eval()` nel RuntimeLoader
15. caricare codice agente in un singolo processo persistente (no module caching cross-run)
16. usare il meta-package `llama-index` invece dei sotto-package specifici

---

## 26. Project structure

```text
aura/
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── routers/
│   │   ├── dependencies/
│   │   └── middleware/
│   ├── worker/
│   │   ├── main.py
│   │   ├── worker_settings.py
│   │   └── jobs/
│   │       ├── ingestion.py
│   │       ├── runtime.py
│   │       └── identity_sync.py
│   └── frontend/
├── aura/
│   ├── domain/
│   │   ├── contracts.py          # tutti i contratti §8
│   │   ├── policies.py           # ModelPolicy, PiiPolicy, SandboxPolicy, profiles
│   │   └── enums.py
│   ├── adapters/
│   │   ├── db/
│   │   │   ├── models.py         # SQLAlchemy ORM
│   │   │   └── session.py
│   │   ├── qdrant/
│   │   ├── s3/
│   │   ├── litellm/
│   │   ├── langfuse/
│   │   ├── presidio/
│   │   ├── sandbox/
│   │   │   ├── provider.py       # SandboxProvider Protocol
│   │   │   ├── docker.py         # DockerSandboxProvider
│   │   │   └── k8s.py            # K8sJobSandboxProvider
│   │   ├── runtime/
│   │   │   └── loader.py         # RuntimeLoader
│   │   └── connectors/
│   │       ├── base.py           # ConnectorWrapper Protocol
│   │       ├── sharepoint.py
│   │       └── ...
│   ├── services/
│   │   ├── retrieval.py
│   │   ├── chat.py
│   │   ├── ingestion.py
│   │   ├── agent.py
│   │   ├── registry.py
│   │   ├── skill.py
│   │   ├── pii.py
│   │   ├── policy.py
│   │   ├── conversation.py
│   │   └── identity_sync.py
│   ├── schemas/
│   │   └── api/                  # request/response pubblici (§21)
│   └── utils/
│       ├── audit.py
│       ├── secrets.py            # SecretStore abstraction
│       └── observability.py
├── registries/
│   ├── prompts/defaults/         # fallback prompt files
│   └── sandbox_profiles/         # profili sandbox predefiniti YAML
├── infra/
│   ├── docker-compose.yml
│   ├── k8s/
│   └── alembic/
│       ├── env.py
│       └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── e2e/
└── docs/
    └── CLAUDE.md                 # vedere §32
```

### Regola strutturale

- `routers/` → solo HTTP mapping, zero business logic
- `services/` → tutta la business logic, zero HTTP
- `adapters/` → integrazione tecnica (DB, S3, Qdrant, etc.)
- `domain/` → contratti, modelli, enums
- `schemas/` → request/response esterni (sottoinsiemi dei contratti)

---

## 27. Implementation order for coding agents

Questa sequenza è obbligatoria.

### Fase 0 — Foundation
1. settings e config (pydantic-settings)
2. engine/session factory + connect hook RLS
3. alembic: env.py + migration iniziale
4. health endpoint
5. ARQ skeleton (worker_settings)
6. docker-compose local infra (postgres, redis, qdrant, minio, litellm)

### Fase 1 — Identity
1. JWT validation middleware (Okta JWKS)
2. `UserIdentity` e `RequestContext` dal token
3. DB session lifecycle dependency
4. RLS middleware + `set_tenant_rls`
5. `/me` endpoint
6. Test: cross-tenant isolation

### Fase 2 — Spaces
1. ORM models e migration: `knowledge_spaces`, `space_memberships`
2. CRUD spaces (create, read, list, archive)
3. ACL filtering su query
4. Test: utente vede solo i propri spaces

### Fase 3 — Upload e ingestion
1. S3 adapter (boto3)
2. Datasource upload API + job enqueue
3. Ingestion job (LlamaIndex parser)
4. Document versioning
5. Embedding via LiteLLM + Qdrant upsert
6. Payload standard §11.3
7. Test: documento indicizzato e recuperabile

### Fase 4 — Retrieval e chat
1. RetrievalService + filter builder
2. Prompt stack builder
3. ChatService non-streaming
4. ChatService streaming (SSE)
5. Citations e conversation persistence
6. Test: retrieval rispetta ACL, citations corrette

### Fase 5 — Policies e PII
1. ModelPolicy, PiiPolicy, RetrievalProfile, EmbeddingProfile, ToneProfile come entità DB
2. PolicyService.resolve_*
3. PiiService batch (Presidio)
4. Sink-specific masking (logs, traces, persistence)
5. Conservative streaming behavior
6. Test: no raw PII in logs con policy attiva

### Fase 6 — Connectors enterprise
1. ConnectorWrapper Protocol + SecretStore abstraction
2. Primo connector (e.g. SharePoint)
3. ACL normalization → NormalizedACL
4. Identity sync job (Okta → users/groups DB)
5. Stale handling + freshness metric
6. Test: ACL materializzate corrette dopo sync

### Fase 7 — Agent registry
1. Manifest validation (Pydantic + YAML)
2. RegistryService: upload/validate/publish flow
3. RuntimeLoader (importlib, temp dir, SHA verify)
4. AgentService.run_agent
5. Agent APIs
6. Agent-as-tool (per orchestrator type)
7. Test: agent non-published non eseguibile; PII rispettato

### Fase 8 — Skills e sandbox
1. SandboxProvider Protocol
2. DockerSandboxProvider (dev)
3. K8sJobSandboxProvider (prod)
4. Skill manifest + run flow
5. Artifact persistence
6. Skill admin APIs
7. Test: sandbox non può uscire dalla rete; timeout rispettato

### Fase 9 — Ops e hardening
1. Langfuse integration + prompt fallback
2. OTel/LGTM: metriche §23.3
3. Degraded modes verificati
4. Retry/idempotency hardening
5. Critical failure tests §28.2
6. Load test baseline (traffico moderato)

---

## 28. Test strategy

### 28.1 Test types

- **unit**: singolo service/adapter, mock delle dipendenze
- **integration**: service + adapter reale (testcontainers per DB, Qdrant, Redis)
- **contract**: verifica che i contratti §8 siano rispettati (schema validation)
- **e2e**: flusso completo via API HTTP

### 28.2 Critical failure tests obbligatori

1. **Tenant isolation**: utente tenant-A non vede dati tenant-B (DB + Qdrant)
2. **Stale source ACL**: documento con ACL revocata non appare in retrieval dopo re-sync
3. **Stale identity mapping**: utente rimosso dal gruppo non accede dopo sync
4. **No raw PII in logs/traces**: con PiiPolicy attiva, assertion su log output
5. **Retry/idempotency**: job lanciato 2 volte produce lo stesso risultato
6. **Job locks**: due worker non processano lo stesso job contemporaneamente
7. **Runtime artifact immutability**: tentativo di run su artifact non-published → 403
8. **Trace propagation**: trace_id presente in risposta API e in log worker
9. **Fallback prompt correctness**: Langfuse down → fallback file usato correttamente
10. **Connector temporary failure**: sync fallisce e riprende con retry; indice precedente intatto
11. **Secret never serialized**: `ResolvedCredentials` non appare in nessun log o payload ARQ
12. **Sandbox escape prevention**: skill che tenta network call → bloccata da SandboxPolicy

---

## 29. Definition of Done

Una feature è **done** solo se:

- rispetta i contratti di questa specifica
- ha test o verifica ripetibile (unit o integration)
- non viola tenancy o PII
- è osservabile (metriche e log minimi)
- non introduce anti-pattern (§25)
- non introduce dipendenze non approvate (§3)
- ha comportamento degradato definito se necessario (§24)
- la Definition of Done è verificata prima del merge

---
