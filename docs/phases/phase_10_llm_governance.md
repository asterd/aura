# Fase 10 — LLM Provider Governance e Cost Management
> AURA Backbone v4.3 · Fase 10 di 10
> **Prerequisito**: Fase 9 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.8, §8.12, §8.13 nuovi contratti LLM governance)
docs/spec/02_services.md    (§7.3 ChatService; §7.5 AgentService; nuova sezione LLM provider governance)
docs/spec/05_api.md         (nuovi endpoint admin LLM)
docs/spec/06_ops.md         (§23 metriche; nuova sezione cost governance)
docs/spec/07_db_schema.md   (nuove tabelle provider/config/budget)
```

---

## Obiettivo

Formalizzare e implementare uno strato enterprise-ready per:

- censimento centralizzato dei provider LLM supportati
- registrazione sicura delle credenziali da parte di amministratori tenant
- abilitazione tenant-level di provider e modelli
- emissione di virtual key / chiave runtime risolta lato backend
- cost management con budget e gate per tenant, utente, provider e progetto/spazio
- sync best-effort di tenant runtime key sulle API admin native di LiteLLM

---

## Tasks obbligatori

### 10.1 — Provider registry

Introdurre un registro provider centralizzato:

- provider canonicali: `openai`, `anthropic`, `azure_openai`, `google_vertex`, `bedrock`, `mistral`, `custom_openai_compatible`
- capability flags: `supports_chat`, `supports_embeddings`, `supports_reasoning`, `supports_tools`
- metadati endpoint/base URL per provider
- stato: `active`, `disabled`, `deprecated`

### 10.2 — Tenant provider credentials

Consentire a utenti amministratori di tenant di censire credenziali provider:

- secret storage via `secret_ref`, mai API key persistita in chiaro
- naming e ownership per tenant
- possibilità di più credenziali per provider
- flag `is_default`

### 10.3 — Tenant model enablement

Un tenant deve poter abilitare uno o più modelli per provider:

- mapping `tenant -> provider credential -> model_name`
- task type: `chat`, `embedding`, `rerank`
- alias opzionale tenant-level
- rate limits / concurrency cap opzionali
- stato `enabled` / `disabled`

### 10.4 — Runtime resolution

ChatService, Retrieval/Embedding path e AgentService devono risolvere:

1. modello richiesto o di default dalla policy
2. entry tenant abilitata per quel modello
3. credenziale corretta
4. virtual key / runtime key da usare verso LiteLLM

### 10.5 — Cost management

Implementare budget e gate su più livelli:

- tenant
- user
- provider
- space / progetto

Ogni budget deve poter avere:

- finestra temporale: `daily`, `monthly`
- hard limit USD
- soft limit USD opzionale
- action on hard limit: `block`, `warn_only`

### 10.6 — Enforcement points

I gate di costo devono essere verificati:

- prima di una model call chat
- prima di una embedding batch call
- prima di un agent run

Inoltre il sistema deve registrare usage/costi stimati o reali per:

- tenant
- user
- provider
- model
- space/progetto
- conversation/run quando presenti

### 10.7 — API admin

Esporre endpoint admin per:

- registrare provider credential
- listare provider supportati
- abilitare modelli per tenant
- configurare budget
- visualizzare usage aggregato e stato budget

---

## Acceptance criteria

- un tenant admin può registrare una credenziale provider senza salvare la chiave in chiaro nel DB
- un tenant admin può abilitare `gpt-4o` e `text-embedding-3-small` su un provider configurato
- ChatService rifiuta model call se il modello non è abilitato per il tenant
- AgentService non usa più una chiave hardcoded, ma una chiave runtime risolta
- cost gate hard limit blocca la chiamata con errore esplicito
- usage aggregato per tenant/provider/modello viene persistito
- tutte le chiavi/secret continuano a non apparire in log o payload ARQ

---

## Note per Claude Code

- mantenere l’architettura LiteLLM-centrica: AURA governa provider, modelli, budget e credenziali; LiteLLM resta il proxy di esecuzione
- non introdurre provider SDK diretti nel core runtime chat/agent
- se un provider richiede endpoint custom, modellarlo come configurazione del provider o della credential, non come hardcode di servizio
- il cost management deve essere fail-closed sui gate hard limit
- delegare a LiteLLM solo gli aspetti compatibili con primitive native di key management (`models`, `max_budget`, `rpm_limit`)
- mantenere in AURA l'enforcement più granulare su `user`, `provider`, `space`, perché non coincide 1:1 con una singola LiteLLM key
