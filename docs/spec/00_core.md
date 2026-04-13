# AURA Spec — §0-6: Principi, Stack, Decisioni Architetturali
> Source: AURA Backbone v4.3 · Sezioni §0-6
> File di riferimento per ogni sessione Claude Code.

## 0. Come usare questa specifica

Questa specifica è scritta per essere usata da:

- sviluppatori umani
- coding agents come Claude Code o equivalenti
- reviewer tecnici e architetti

Questa versione è ottimizzata per minimizzare:

- interpretazione creativa
- ambiguità tra livelli architetturali
- implementazioni formalmente plausibili ma strutturalmente mediocri
- drift tra API, servizi e persistence

### Obiettivo architetturale

AURA deve essere:

- production-grade
- solida e resiliente
- adatta a traffico moderato
- governabile da un team enterprise
- comprensibile e implementabile correttamente
- **ultra-light**: nessun componente senza ownership chiara, nessuna astrazione senza contratto

### Filosofia ultra-light enterprise

AURA preferisce:

- un componente che fa bene una cosa
- un contratto esplicito rispetto a un'interfaccia implicita
- un fallback definito rispetto a un comportamento opportunistico
- la semplicità operativa rispetto alla flessibilità teorica

### Obiettivo non perseguito

AURA non è ottimizzata per:

- hyperscale internet traffic
- microservizi spinti
- real-time event mesh
- delega live dei permessi da sistemi esterni
- DAG arbitrari complessi di lunga durata

---

## 1. Regole operative per coding agents

Queste regole sono vincolanti.

1. Un task alla volta.
2. Un bounded context per task.
3. Leggere sempre la sezione rilevante prima di scrivere codice.
4. Thin router, heavy service.
5. Framework-first, custom-last.
6. I service methods ricevono dipendenze già risolte.
7. Nessuna business logic nei router, model layer o adapter.
8. No shared state in-memory tra processi.
9. Ogni task deve avere verifica automatizzabile.
10. Ogni placeholder deve essere esplicito con `raise NotImplementedError("reason")`.

### 1.1 Gerarchia normativa

Per ogni sezione si applica questa gerarchia:

1. Decisione
2. Contratto
3. Regole MUST/MUST NOT
4. Pseudocodice normativo
5. Esempio illustrativo
6. Acceptance/Test

### 1.2 Tipi di snippet

Ogni snippet in questo documento è uno dei seguenti:

- **CONTRACT** — da implementare come interfaccia o schema
- **NORMATIVE PSEUDOCODE** — struttura di controllo da rispettare
- **REFERENCE IMPLEMENTATION** — pattern consigliato, adattabile senza violare i contratti
- **ILLUSTRATIVE EXAMPLE** — esempio esplicativo, non vincolante

Se un frammento non è etichettato, va trattato come normativo solo se ricade in una sezione di contratto esplicito.

---

## 2. Executive Summary

AURA è la backbone aziendale unica per:

- knowledge base governate
- retrieval aumentato
- agenti AI governati
- skill sandboxed
- policy centralizzate
- audit ed osservabilità
- API e UI di interazione AI

### 2.1 Forma architetturale finale

AURA è composta da:

- AURA API → FastAPI
- worker-ingestion → ARQ
- worker-runtime → ARQ
- Postgres → source of truth relazionale + RLS
- Redis → queue, lock, cache breve
- Qdrant → retrieval ibrido con payload filtering
- S3-compatible storage → originali, canonical text, artifacts
- LiteLLM → gateway unico modelli
- Langfuse → prompt management e tracing prodotto
- LlamaIndex → parsing, ingestion, retrieval integration
- PydanticAI → runtime agentico
- Presidio → PII layer centralizzato
- OTel + Grafana stack → metriche, log, traces
- Okta OIDC → identity

### 2.2 Filosofia v4.3

Questa versione:

- chiude tutti i contratti aperti della v4.1 (v4.2)
- specifica SandboxProvider, RuntimeLoader e ConnectorCredentials (v4.2)
- fornisce il DB schema baseline obbligatorio (v4.2)
- fornisce il CLAUDE.md template per sessioni di coding agent (v4.2)
- aggiorna le versioni stack a dati verificati PyPI aprile 2026 (v4.3)
- chiude i gap di sicurezza RLS identificati dalla verifica (v4.3)
- aggiunge rationale esplicito sulla scelta PydanticAI vs Agno (v4.3)

---

## 3. Stack tecnologico approvato

Il coding agent MUST usare queste versioni o minor compatibili espressamente approvate nel file di config del progetto.

| Componente | Versione approvata | Note |
|---|---:|---|
| Python | 3.12.x | |
| FastAPI | 0.115.x | |
| Uvicorn | 0.29.x | |
| Pydantic | 2.7.x | |
| pydantic-settings | 2.3.x | |
| SQLAlchemy | 2.0.x | async engine obbligatorio |
| Alembic | 1.13.x | |
| asyncpg | 0.29.x | |
| Redis Python | 5.0.x | |
| ARQ | 0.25.x | |
| httpx | 0.27.x | |
| boto3 | 1.34.x | |
| Qdrant client | 1.9.x | |
| llama-index-core | 0.10.x | ⚠️ Usare `llama-index-core`, non il meta-package `llama-index`. Verificare PyPI prima di iniziare Fase 3. |
| llama-index-readers-file | 0.1.x | per parsing locale |
| llama-index-embeddings-litellm | 0.1.x | via LiteLLM proxy |
| PydanticAI | >= 1.0, serie 1.x (current: 1.79.x) | ✅ V1 stabile da settembre 2025. API stability commitment attivo fino a V2. Vincolare a `pydantic-ai~=1.79` in requirements. Release settimanali, no breaking changes entro la serie 1.x. |
| LiteLLM Proxy | 1.40.x | ⚠️ Il container LiteLLM proxy richiede in produzione ≥ 4 CPU core e ≥ 8 GB RAM. La governance di budget e rate-limit è gestita da AURA (ModelPolicy), non dall'enforcement interno di LiteLLM che presenta bug noti nelle versioni recenti (issue #10052). |
| Langfuse SDK | 3.x | |
| Presidio analyzer | 2.2.x | |
| Presidio anonymizer | 2.2.x | |
| spaCy | 3.7.x | modello `en_core_web_sm` + lingua tenant |
| Next.js | 15.x | |
| React | 19.x | |
| TanStack Query | 5.x | |
| Zustand | 4.x | |

### 3.1 Regola versioning

- versioni patch possono essere aggiornate senza cambiare la specifica
- versioni minor possono cambiare solo dopo validazione CI e aggiornamento esplicito del progetto
- versioni major richiedono revisione architetturale

### 3.2 Dipendenze esplicitamente escluse

Il coding agent MUST NOT introdurre nel core runtime:

- LangChain
- LangGraph
- Celery
- RabbitMQ
- Kafka
- SigNoz
- framework BPM o orchestration aggiuntivi
- il meta-package `llama-index` (usare solo i sotto-package necessari)
- **Agno** (ex Phidata) — escluso per incompatibilità architetturale con AURA, non per qualità. Agno espone il proprio AgentOS come FastAPI runtime autonomo con proprio DB layer e proprio control plane. In AURA il runtime è `AgentService`, il DB è Postgres con RLS, la governance è centralizzata in `PolicyService`/Langfuse/OTel. Integrare Agno significherebbe avere due runtime FastAPI paralleli con ownership ambigua di sessione, policy e audit. **PydanticAI è lo strumento corretto per AURA**: fornisce agent runtime embedded, type-safe, senza infrastruttura propria, perfettamente composabile con il lifecycle di `AgentService`. Agno è la scelta corretta per chi vuole costruire *ex novo* un sistema agentico autonomo, non per chi integra agent runtime in un backbone enterprise governato.

---

## 4. Obiettivi e non-obiettivi

### 4.1 Obiettivi

AURA MUST supportare:

1. chat con retrieval e citations
2. spaces con ACL di spazio e documentali materializzate
3. upload locale e connettori enterprise
4. agent registry con policy, prompt, tools e budget governati
5. skill sandboxed per elaborazioni e artifact
6. deploy affidabile in locale e su cluster
7. audit, tracing e monitoring operativi
8. PII handling centralizzato

### 4.2 Non-obiettivi

AURA MUST NOT diventare:

- una BPM suite
- una mesh di microservizi
- un ETL framework generalista
- una piattaforma internet-scale
- un sistema di live delegated source access come baseline
- un playground agentico senza governance

---

## 5. Principi architetturali permanenti

1. Postgres è la source of truth.
2. Redis è runtime-support, non source of truth.
3. Qdrant è retrieval infrastructure, non transaction store.
4. KnowledgeSpace è il concetto centrale per la conoscenza condivisa.
5. AURA Registry è la source of truth per agenti e skill pubblicati.
6. Tutte le policy sono centrali.
7. Tutta la logica pesante avviene fuori dal request path.
8. Ogni sottosistema critico ha ownership unica.
9. I service contracts vengono prima dell'implementazione.
10. Correttezza e operabilità battono flessibilità e astrazione inutile.

---

## 6. Decisioni architetturali permanenti

### DR-001 — Due worker types nella baseline

**DECISION**: usare solo `worker-ingestion` e `worker-runtime`.

**RATIONALE**: per traffico moderato garantiscono sufficiente isolamento dei workload con complessità operativa ragionevole.

### DR-002 — ACL documentali indicizzate, non live

**DECISION**: la baseline usa `source_acl_enforced` tramite ACL materializzate in Qdrant.

**CONSEGUENZA**: il sistema è eventualmente consistente rispetto ai source permissions.

### DR-003 — Retrieval e generation separati

**DECISION**: `RetrievalService` e `ChatService` sono servizi distinti con I/O separati.

### DR-004 — Langfuse come source of truth dei prompt

**DECISION**: i prompt sono gestiti in Langfuse, con fallback a file bundled in repo.

### DR-005 — LiteLLM come gateway unico

**DECISION**: tutte le model calls passano da LiteLLM, incluse quelle di embedding.

### DR-006 — RLS obbligatoria

**DECISION**: l'isolamento tenant è implementato con PostgreSQL RLS + `SET LOCAL app.current_tenant_id`.

### DR-007 — Runtime canonico da artifact immutabili

**DECISION**: agenti e skill eseguibili in produzione devono essere caricati solo da artifact versionati immutabili e record DB `published`.

### DR-008 — Sandbox locale/cluster

**DECISION**: baseline: dev locale → Docker effimero; cluster → K8s Job isolato.

### DR-009 — PII streaming conservativo

**DECISION**: la baseline non promette pseudonymization sofisticata token-by-token su streaming continuo.

### DR-010 — No service-created DB session

**DECISION**: i service methods ricevono sempre una `AsyncSession` già creata e già contestualizzata.

### DR-011 — Policy come entità DB, non configurazione

**DECISION**: ModelPolicy, PiiPolicy, SandboxPolicy, RetrievalProfile, EmbeddingProfile e ToneProfile sono record DB per tenant, non file di configurazione.

**RATIONALE**: permette governance, audit e override per space senza deploy.

### DR-012 — RuntimeLoader via importlib su temp dir isolata

**DECISION**: gli agent artifact vengono estratti in una temp dir per-run e importati via `importlib`. Nessun `exec()` diretto. La temp dir viene rimossa al termine del run.

**RATIONALE**: sicurezza e tracciabilità. Il codice non persiste tra run nel worker.

### DR-013 — ConnectorCredentials sempre da secret store

**DECISION**: le credenziali non vengono mai serializzate nei record DB in chiaro. Il DB conserva solo un `secret_ref` che punta al secret store (Vault, AWS Secrets Manager, K8s Secret).

### DR-014 — Embedding sempre via LiteLLM proxy

**DECISION**: nessun client embedding diretto. Tutti gli embedding passano da LiteLLM con virtual key per tenant. Consente rate limiting, routing e audit uniformi.

---
