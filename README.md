# AURA Dev Kit — Guida all'implementazione con Claude Code
> AURA Backbone v4.3 · Aprile 2026

Questo kit contiene tutto il necessario per implementare AURA da zero usando Claude Code in sessioni bounded per fase. Ogni fase ha il proprio file con tasks, acceptance criteria e note operative.

---

## Struttura del kit

```
CLAUDE.md                          ← Leggi in OGNI sessione
docs/
  spec/
    00_core.md                     ← Regole, stack, decisioni arch. (§0-6)
    01_contracts.md                ← Contratti Pydantic — non modificare (§8)
    02_services.md                 ← Service boundaries, RLS, chat, PII (§7,9,10,13-16)
    03_knowledge.md                ← Knowledge backbone, retrieval (§11-12)
    04_agents.md                   ← Agent runtime, registry, sandbox, connectors (§17-20)
    05_api.md                      ← API surface e schemas (§21)
    06_ops.md                      ← Jobs, observability, degraded modes, DoD (§22-29)
    07_db_schema.md                ← Schema DB completo con RLS (§31)
    08_ux_architecture.md          ← UX: threading, streaming, composer, sidebar, artifact viewer (§35)
    09_triggered_agents.md         ← Triggered & autonomous agents, cron/event, webhook (§36)
    10_mcp_bridge.md               ← MCP Bridge: AURA server + skill mcp_client (§37)
    11_agent_chat_integration.md   ← Agent-in-chat: @mention, AgentChatService, stream events (§38)
  phases/
    phase_0_foundation.md          ← Infra, settings, health, ARQ skeleton
    phase_1_identity.md            ← JWT, UserIdentity, RLS, /me
    phase_2_spaces.md              ← CRUD spaces, ACL, memberships
    phase_3_ingestion.md           ← S3, LlamaIndex, Qdrant upsert
    phase_4_retrieval_chat.md      ← RetrievalService, ChatService, SSE
    phase_5_policies_pii.md        ← ModelPolicy, PiiPolicy, Presidio
    phase_6_connectors.md          ← ConnectorWrapper, SecretStore, identity sync
    phase_7_agents.md              ← Agent registry, RuntimeLoader, AgentService + triggered/chat
    phase_8_skills_sandbox.md      ← SandboxProvider, Docker, skill run + MCP Bridge
    phase_9_ops.md                 ← Langfuse, OTel, degraded modes, critical tests
    phase_10_ui.md                 ← Next.js shell, chat, spaces, agents UI
```

---

## Principio fondamentale

**Una sessione = una fase.**
Non caricare più fasi insieme. Non passare alla fase N+1 prima che i test della fase N siano verdi.

Il file `CLAUDE.md` va sempre incluso. I file spec vanno caricati selettivamente — solo quelli indicati nel file di fase.

---

## Come avviare ogni sessione — Prompt template

### Prompt di avvio sessione (generico)

Copia questo prompt all'inizio di ogni sessione Claude Code, adattando `N`:

```
Implementa la Fase N di AURA.

Leggi questi file in questo ordine prima di scrivere qualsiasi codice:
1. CLAUDE.md
2. docs/phases/phase_N_<nome>.md
3. I file spec indicati nella sezione "File da leggere" del file di fase

Regole:
- Rispetta i contratti di docs/spec/01_contracts.md — non ridefinirli inline
- Ogni placeholder: raise NotImplementedError("reason")
- La fase è DONE solo quando tutti gli acceptance criteria del file di fase sono verdi
- Non iniziare task fuori dallo scope di questa fase

Prima di iniziare: elenca i file che leggerai e conferma di aver capito i task obbligatori.
```

## Prompt di verifica step

Ho fatto implementare quanto indicato nel prompt che ti incollo di seguito.
Mi verifichi che l'implementazione fatta sia corretta?
NB. la modifica non è ancora committata
"
<prompt here>
"

---

## Prompt specifici per ogni fase

### Fase 0 — Foundation

```
Implementa la Fase 0 di AURA (Foundation).

Leggi questi file prima di scrivere codice:
1. CLAUDE.md
2. docs/phases/phase_0_foundation.md
3. docs/spec/00_core.md (solo §3: stack tecnologico)
4. docs/spec/07_db_schema.md (solo §31.1: tabella tenants)

I deliverable di questa fase sono:
- apps/api/config.py (pydantic-settings, fail-fast su variabili mancanti)
- aura/adapters/db/session.py (engine, AsyncSessionLocal, connect hook RLS, set_tenant_rls)
- infra/alembic/ (env.py + migration 001 tabella tenants)
- apps/api/main.py (solo /health endpoint)
- apps/worker/worker_settings.py (ARQ skeleton con 2 job placeholder)
- infra/docker-compose.yml (postgres, redis, qdrant, minio, litellm-proxy)

La fase è done quando il gate di acceptance criteria in phase_0_foundation.md è tutto verde.
Inizia leggendo i file elencati.
```

---

### Fase 1 — Identity

```
Implementa la Fase 1 di AURA (Identity).

Prerequisito: i test di Fase 0 sono verdi (health endpoint risponde, RLS funziona, alembic up).

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_1_identity.md
3. docs/spec/01_contracts.md (§8.1: UserIdentity, RequestContext)
4. docs/spec/02_services.md (§9: Identity model; §10: RLS lifecycle completo)
5. docs/spec/07_db_schema.md (§31.1: tabelle users, groups, user_group_memberships)

Non toccare nessun file fuori da questo scope.
Inizia con la migration delle tabelle identity (task 1.1).
La fase è done quando test_cross_tenant_isolation passa.
```

---

### Fase 2 — Spaces

```
Implementa la Fase 2 di AURA (Spaces).

Prerequisito: test_cross_tenant_isolation di Fase 1 verde.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_2_spaces.md
3. docs/spec/01_contracts.md (§8.1 UserIdentity; §8.8 EmbeddingProfile, RetrievalProfile, ToneProfile)
4. docs/spec/03_knowledge.md (§11.1: KnowledgeSpace contract)
5. docs/spec/07_db_schema.md (§31.2: knowledge_spaces, space_memberships; §31.5: profile tables)

Inizia dalla migration (task 2.1).
La fase è done quando test_user_sees_only_own_spaces e test_non_member_cannot_access_space passano.
```

---

### Fase 3 — Upload e Ingestion

```
Implementa la Fase 3 di AURA (Upload e Ingestion).

Prerequisito: Fase 2 verde.

⚠️ Prima di iniziare: esegui `pip show llama-index` — se è installato il meta-package, rimuovilo.
Usare SOLO: llama-index-core, llama-index-readers-file, llama-index-embeddings-litellm.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_3_ingestion.md
3. docs/spec/01_contracts.md (§8.4: LoadedDocument, DocumentMetadata, NormalizedACL)
4. docs/spec/03_knowledge.md (§11.2: document lifecycle; §11.3: payload Qdrant COMPLETO)
5. docs/spec/07_db_schema.md (§31.2: datasources, documents, document_versions)
6. docs/spec/06_ops.md (§22: job keys, retry policy)

Il payload Qdrant deve includere TUTTI i campi di §11.3 — verificalo prima di fare l'upsert.
La fase è done quando test_upload_and_ingest_e2e e test_cross_tenant_qdrant_isolation passano.
```

---

### Fase 4 — Retrieval e Chat

```
Implementa la Fase 4 di AURA (Retrieval e Chat).

Prerequisito: Fase 3 verde — un documento indicizzato in Qdrant.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_4_retrieval_chat.md
3. docs/spec/01_contracts.md (§8.2 Retrieval contracts; §8.3 Chat contracts)
4. docs/spec/02_services.md (§7.2 RetrievalService MUST/MUST NOT; §7.3 ChatService MUST/MUST NOT; §12 retrieval arch; §13 prompt stack ORDER; §14 prompt mgmt; §15 chat pseudocode)
5. docs/spec/03_knowledge.md (§12.3: filter builder — campo per campo)

ATTENZIONE: il prompt stack (§13) ha un ordine obbligatorio di 8 livelli. Non riordinarlo.
ATTENZIONE: RetrievalService NON chiama LiteLLM per generation. ChatService NON interroga Qdrant.
La fase è done quando test_chat_respond_with_citations e test_chat_stream_events_typed passano.
```

---

### Fase 5 — Policies e PII

```
Implementa la Fase 5 di AURA (Policies e PII).

Prerequisito: Fase 4 verde.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_5_policies_pii.md
3. docs/spec/01_contracts.md (§8.9 ModelPolicy; §8.10 PiiPolicy con tabella normativa; §8.11 SandboxPolicy)
4. docs/spec/02_services.md (§7.7 PiiService; §7.9 PolicyService; §16 PII specification)
5. docs/spec/07_db_schema.md (§31.5: model_policies, pii_policies, sandbox_policies)

La tabella normativa PiiMode in §8.10 è vincolante — implementa ogni mode esattamente come descritto.
La fase è done quando test_no_raw_pii_in_logs e test_model_override_not_in_allowlist_rejected passano.
```

---

### Fase 6 — Connectors Enterprise

```
Implementa la Fase 6 di AURA (Connectors Enterprise).

Prerequisito: Fase 5 verde.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_6_connectors.md
3. docs/spec/01_contracts.md (§8.4 NormalizedACL, LoadedDocument; §8.12 ConnectorCredentials, ResolvedCredentials)
4. docs/spec/04_agents.md (§20: ConnectorWrapper Protocol; §20.2 failure behavior table; §20.3 credential resolution)
5. docs/spec/07_db_schema.md (§31.2: datasources.credentials_ref)
6. docs/spec/06_ops.md (§22.4: retry policy connector-sync)

CRITICO: ResolvedCredentials NON viene mai passato come payload ARQ.
Il job riceve solo secret_ref e risolve autonomamente.
La fase è done quando test_credentials_never_serialized e test_stale_acl_after_sync passano.
```

---

### Fase 7 — Agents

```
Implementa la Fase 7 di AURA (Agents).

Prerequisito: Fase 6 verde.

⚠️ Verifica: `pip show pydantic-ai` deve mostrare versione 1.79.x.

Leggi questi file:
1. CLAUDE.md (rilleggi §PydanticAI agent pattern)
2. docs/phases/phase_7_agents.md
3. docs/spec/01_contracts.md (§8.5 AgentDeps, AgentRunRequest, AgentRunResult)
4. docs/spec/04_agents.md (§17.3 run_agent pseudocode; §17.5 reference implementation; §18 registry flow; §19.5 RuntimeLoader contract)
5. docs/spec/07_db_schema.md (§31.4: agent_packages, agent_versions, agent_runs)
6. docs/spec/09_triggered_agents.md (§36 completo — triggered & autonomous)
7. docs/spec/11_agent_chat_integration.md (§38 completo — @mention, AgentChatService)

Scope di questa fase:
- AgentService.run_agent (pseudocodice §17.3 — 10 step in ordine)
- RuntimeLoader via importlib (mai exec/eval)
- RegistryService + publish flow (§18)
- TriggerSchedulerService e EventDispatcherService (§36) con migration agent_trigger_registrations
- AgentChatService con @mention parsing e streaming eventi agent_running/agent_done (§38)
- Nuovi contratti in contracts.py: CronTrigger, EventTrigger, InternalEvent, AgentInvocation, AgentChatInput
- Endpoint POST /api/v1/webhooks/{agent_name}/inbound (HMAC-SHA256)
- Endpoint GET /api/v1/conversations e /api/v1/conversations/{id}

CRITICO: RuntimeLoader usa importlib, mai exec()/eval().
CRITICO: TriggerSchedulerService NON apre sessioni autonome — riceve session iniettata.
CRITICO: AgentChatService NON genera testo — delega sempre a ChatService.
CRITICO: run agente falliti NON bloccano la risposta — catturati con return_exceptions=True.
La fase è done quando test_non_published_agent_not_executable, test_cron_trigger_fires_on_schedule e test_agent_mention_invokes_agent passano.
```

---

### Fase 8 — Skills, Sandbox e MCP

```
Implementa la Fase 8 di AURA (Skills, Sandbox e MCP).

Prerequisito: Fase 7 verde.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_8_skills_sandbox.md
3. docs/spec/01_contracts.md (§8.11 SandboxPolicy; §8.12 ResolvedCredentials)
4. docs/spec/04_agents.md (§19: SandboxProvider Protocol; §19.3 SandboxInput/SandboxResult; §19.4 DockerSandboxProvider reference impl)
5. docs/spec/10_mcp_bridge.md (§37 completo — skill mcp_client e AURA MCP Server)

Scope di questa fase:
- DockerSandboxProvider (network_egress=none di default, memory limit, timeout)
- RuntimeLoader SHA256 verify + per-run temp dir cleanup
- Skill type mcp_client nel manifest validator
- McpBridgeAdapter Protocol + implementazione HTTP/SSE client
- AgentDeps esteso con mcp_adapters: dict[str, McpBridgeAdapter]
- Nuovi contratti in contracts.py: McpToolDefinition, McpToolResult
- AURA MCP Server: endpoint /mcp/v1/sse con tool aura_retrieve, aura_chat, aura_agent_run, aura_list_spaces, aura_list_agents

CRITICO: la skill mcp_client (outbound) va implementata PRIMA del MCP Server (inbound).
CRITICO: McpBridgeAdapter NON viene istanziato nei router — sempre via dependency injection.
CRITICO: il MCP Server rispetta RLS e policy — nessun bypass.
La fase è done quando test_sandbox_network_blocked, test_sandbox_timeout_respected e test_mcp_server_rls_enforced passano.
```

---

### Fase 9 — Ops e Hardening

```
Implementa la Fase 9 di AURA (Ops e Hardening).

Prerequisito: Fase 8 verde.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_9_ops.md
3. docs/spec/06_ops.md (§23: metriche obbligatorie; §24: degraded modes; §28.2: critical failure tests COMPLETI)
4. docs/spec/02_services.md (§14: prompt management fallback)

La fase è done solo quando TUTTI e 12 i critical failure tests di §28.2 passano.
Questi test non sono opzionali — sono il gate finale di produzione.
```

---

### Fase 10 — UI

```
Implementa la Fase 10 di AURA (UI).

Prerequisito: Fase 4 verde (chat/stream funziona). Le funzionalità avanzate (agenti, artifact) richiedono Fase 7 verde.
Stack: Next.js 15, React 19, Zustand (state), Tailwind CSS.

Leggi questi file:
1. CLAUDE.md
2. docs/phases/phase_10_ui.md
3. docs/spec/08_ux_architecture.md (§35 completo)
4. docs/spec/01_contracts.md (§8.3 ChatStreamEvent — tutti i tipi inclusi agent_running e agent_done)
5. docs/spec/05_api.md (tutti gli endpoint UI-facing: /me, /chat/stream, /conversations, /agents, /datasources/upload)

Scope di questa fase:
- Layout con sidebar (thread history, spaces, agents)
- Login/redirect JWT
- Composer con @agent-name e #space-name mention, drag-and-drop upload
- MessageBubble streaming: PENDING → STREAMING → DONE | ERROR, debounce 50ms, retry SSE
- CitationCard inline
- Indicatori agent_running / agent_done tra invio e token streaming
- ArtifactRenderer (markdown, code, csv, json, pdf_preview, image, unknown)

CRITICO: nessun dato sensibile in localStorage/sessionStorage.
CRITICO: il Composer NON invia durante STREAMING.
CRITICO: artifact sempre via URL firmato S3 — mai base64 nel body.
La fase è done quando chat streaming end-to-end funziona con citations, e @mention agente produce artifact renderizzato.
```

---

## Regole di ingaggio per Claude Code

### All'inizio di ogni sessione
1. Leggi `CLAUDE.md` per intero
2. Leggi il file di fase
3. Leggi i file spec indicati nella sezione "File da leggere"
4. Elenca i task che farai e conferma di aver capito lo scope
5. **Non iniziare a scrivere codice finché non hai letto tutto**

### Durante la sessione
- Se trovi un contratto non definito: importalo da `aura/domain/contracts.py`, non ridefinirlo
- Se hai un dubbio su un boundary di service: rileggi `docs/spec/02_services.md §7`
- Se devi scegliere tra due approcci: scegli quello più semplice che rispetta il contratto
- Se un task supera lo scope della fase: usa `raise NotImplementedError("out of scope: fase N")` e documenta

### Prima di dichiarare una fase done
- Esegui tutti gli acceptance criteria della fase
- Verifica che nessun anti-pattern di `CLAUDE.md` sia stato introdotto
- Verifica con `pip show agno langchain langgraph` che nessuna dipendenza vietata sia stata aggiunta
- Verifica che `aura/domain/contracts.py` non sia stato modificato senza necessità

---

## Setup iniziale del repo

```bash
# 1. Clona / crea repo
git init aura
cd aura

# 2. Copia questo kit in docs/
cp -r aura-dev-kit/docs ./docs
cp aura-dev-kit/CLAUDE.md ./CLAUDE.md

# 3. Crea struttura directory progetto
mkdir -p apps/api/routers apps/api/dependencies apps/api/middleware
mkdir -p apps/worker/jobs
mkdir -p aura/domain aura/adapters/db aura/adapters/qdrant aura/adapters/s3
mkdir -p aura/adapters/litellm aura/adapters/langfuse aura/adapters/presidio
mkdir -p aura/adapters/sandbox aura/adapters/runtime aura/adapters/connectors
mkdir -p aura/adapters/registry aura/services aura/schemas/api aura/utils
mkdir -p registries/prompts/defaults registries/sandbox_profiles
mkdir -p infra/alembic/versions infra/k8s
mkdir -p tests/unit tests/integration tests/contract tests/e2e tests/critical

# 4. Crea .env dal template (dopo Fase 0)
cp .env.example .env

# 5. Avvia infra locale (dopo Fase 0)
docker compose -f infra/docker-compose.yml up -d
```

---

## Troubleshooting sessioni Claude Code

**Problema**: Claude Code ha perso il filo dei contratti dopo molti file generati.
**Soluzione**: Inizia una nuova sessione. Fornisci: `CLAUDE.md` + `docs/spec/01_contracts.md` + il file di fase corrente + i file già creati rilevanti per quella fase.

**Problema**: Claude Code ha introdotto una dipendenza non approvata.
**Soluzione**: `pip uninstall <pkg>` + nuova sessione con prompt che include esplicitamente "Non usare <pkg>. Usa invece <alternativa approvata>."

**Problema**: Un acceptance criteria non passa ma il codice sembra corretto.
**Soluzione**: Rileggi il contratto esatto in `docs/spec/01_contracts.md`. Il 90% dei casi è un campo mancante o un ordine sbagliato (es. prompt stack, PII pipeline).

**Problema**: La sessione è diventata lunga e Claude Code inizia a fare scelte incoerenti.
**Soluzione**: Ferma la sessione. Fai un commit di ciò che funziona. Inizia una nuova sessione fornendo solo i file rilevanti per il task specifico rimanente.
