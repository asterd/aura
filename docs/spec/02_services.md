# AURA Spec — §7,9,10,13-16: Service Boundaries, Identity, RLS, Chat, PII
> Source: AURA Backbone v4.3

## 7. Service boundaries

Questa sezione è vincolante.

### 7.1 AURA API

MUST:
- autenticare
- autorizzare
- costruire request context
- aprire transaction scope
- impostare tenant context
- orchestrare servizi
- serializzare response/SSE
- emettere audit e trace di livello request

MUST NOT:
- fare parsing pesante
- fare embedding
- eseguire sandbox
- fare reindex massivi
- importare direttamente codice agentico
- usare Qdrant direttamente senza service boundary

### 7.2 RetrievalService

MUST:
- costruire retrieval filters
- eseguire retrieval ibrido
- rerankare
- assemblare context
- normalizzare citations candidate

MUST NOT:
- chiamare LiteLLM per generation
- persistere messaggi
- applicare output masking
- emettere SSE
- accedere direttamente ai router

### 7.3 ChatService

MUST:
- ricevere un `RetrievalResult`
- comporre prompt stack
- applicare policy PII/guardrail/model
- chiamare LiteLLM
- filtrare output
- persistere messaggi e citations
- restituire eventi di streaming strutturati

MUST NOT:
- interrogare Qdrant direttamente
- costruire filtri ACL da zero
- implementare retrieval
- accedere direttamente al layer HTTP

### 7.4 IngestionService

MUST:
- fetch documenti
- canonicalizzare
- estrarre metadata
- gestire versioning documenti
- orchestrare chunking, embedding e upsert
- aggiornare stati di lifecycle

MUST NOT:
- chiamare modelli generativi per chat
- bypassare object storage
- scrivere direttamente in conversation/message tables

### 7.5 AgentService

MUST:
- risolvere versione pubblicata
- validare permessi
- risolvere policy e prompt
- costruire `AgentDeps`
- istanziare runtime agentico via `RuntimeLoader`
- eseguire run
- persistere `AgentRun`
- gestire artifact e audit

MUST NOT:
- leggere codice non published
- lasciare tool/spaces impliciti
- bypassare LiteLLM
- usare direttamente il layer web
- usare `exec()` direttamente sul codice agent

### 7.6 RegistryService

MUST:
- validare manifest
- gestire lifecycle di versione
- creare record DB
- collegare artifact immutabili
- rifiutare publish non validi

MUST NOT:
- eseguire runtime agentico
- valutare authz utente finale
- mutare artifact già pubblicati

### 7.7 PiiService

MUST:
- rilevare entità
- trasformare testo secondo `PiiPolicy`
- restituire risultato strutturato
- gestire mapping cifrati dove richiesto

MUST NOT:
- applicare politiche implicite
- scrivere in log raw PII
- assumere che lo streaming coincida con il testo completo

### 7.8 Connector Wrappers

MUST:
- adattare credenziali, cursori, metadata e ACL
- normalizzare risultati
- esporre capability dichiarate
- recuperare credenziali solo dal secret store via `secret_ref`

MUST NOT:
- reimplementare crawling già fornito dal connettore base
- nascondere errori di source
- saltare la normalizzazione ACL
- ricevere o loggare credenziali in chiaro

### 7.9 PolicyService

MUST:
- risolvere policy per space o agent version
- restituire entità DB tipizzate (non dict generici)
- applicare precedenza: agent manifest > space > tenant default

MUST NOT:
- fare override di policy senza record audit
- usare policy hardcoded

---

## 9. Identity, tenancy e accesso

### 9.1 Access model

- Layer 1: Identity (JWT → UserIdentity)
- Layer 2: Space ACL (membership table)
- Layer 3: Source ACL materializzata (Qdrant payload filtering)

### 9.2 Modalità baseline

#### `space_acl_only`
Il permesso di spazio è sufficiente.

#### `source_acl_enforced`
Si applicano anche ACL documentali materializzate nell'indice.

#### Non supportato nella baseline
`live_delegated_access`

### 9.3 Invariante di sicurezza

Un utente può vedere un documento solo se:

- appartiene al tenant corretto
- ha accesso allo space
- se `source_acl_enforced`, soddisfa anche l'ACL documentale

### 9.4 Identity sync contract

```python
# CONTRACT
class IdentitySyncResult(BaseModel):
    tenant_id: UUID
    users_seen: int
    users_updated: int
    groups_seen: int
    groups_updated: int
    unmapped_users: int
    partial_failures: int
    completed_at: datetime
```

### Regole identity sync

MUST:
- tracciare `synced_at`
- segnalare mapping mancanti
- marcare stati `partial` o `stale`
- non cancellare mapping in modo distruttivo senza riconciliazione esplicita

MUST NOT:
- assumere che email e UPN siano sempre equivalenti
- considerare sync riuscita se ci sono errori parziali non riportati

### Stato operativo richiesto

Ogni tenant deve avere:

- ultimo sync riuscito
- errore ultimo sync
- freshness in secondi
- numero mapping unmapped

---

## 10. RLS, session lifecycle e transaction discipline

Questa sezione è critica.

### 10.1 Regola fondamentale

Una request HTTP MUST usare una sola `AsyncSession` per il proprio scope logico e una transaction scope esplicita.

### 10.2 Regole vincolanti

- il tenant context deve essere impostato prima di qualsiasi query business
- i service methods ricevono una sessione già pronta
- i service methods MUST NOT creare una nuova sessione tenant-scoped
- i router MUST NOT fare query business
- i worker jobs multi-tenant devono impostare anch'essi il tenant context

### 10.3 CONTRACT — session factory

```python
# CONTRACT
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

### 10.4 REFERENCE IMPLEMENTATION — connect hook

```python
# REFERENCE IMPLEMENTATION
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET app.current_tenant_id = ''")
    cursor.close()
```

### 10.5 NORMATIVE PSEUDOCODE — API request lifecycle

```python
# NORMATIVE PSEUDOCODE
async def request_lifecycle():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, tenant_id)
            request.state.db = session
            request.state.tenant_id = tenant_id
            response = await call_service_layer(session=session, ...)
        return response
```

### 10.6 NORMATIVE PSEUDOCODE — worker lifecycle

```python
# NORMATIVE PSEUDOCODE
async def run_tenant_scoped_job(payload: JobPayload):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, payload.tenant_id)
            await execute_job_logic(session=session, payload=payload)
```

### 10.7 Regola SQL raw

`text()` è vietato per business query ordinarie.
È ammesso per:

- `SET LOCAL`
- readiness checks
- migration Alembic
- query analitiche giustificate e commentate

### 10.8 ⚠️ Nota critica: pgbouncer e SET LOCAL

AURA usa il pool nativo asyncpg (`AsyncSessionLocal`) senza pgbouncer interposto tra applicazione e Postgres. Questa è la configurazione corretta.

**Se in futuro viene aggiunto pgbouncer per scaling**: `SET LOCAL` (usato per impostare `app.current_tenant_id`) è incompatibile con pgbouncer in modalità `transaction` o `statement`. In quelle modalità la variabile di sessione può leakare tra connessioni di utenti diversi, causando violazioni di tenancy silenziose — non errori visibili.

Se pgbouncer viene introdotto, MUST usare `pool_mode = session`. Questa decisione richiede revisione architetturale e aggiornamento esplicito di questa sezione.

---

## 13. Prompt stack

Ordine obbligatorio (livelli superiori non sovrascrivibili da quelli inferiori):

1. `platform_system_prompt`
2. `tenant_tone_prompt`         ← da ToneProfile.prompt_snippet
3. `guardrail_policy_prompt`    ← da PolicyService
4. `space_system_instructions`  ← da KnowledgeSpace.system_instructions
5. `agent_prompt`               ← da Langfuse (se agent run)
6. `user_additional_instructions`
7. `retrieved_context_block`
8. `current_user_message`

Regole:
- i livelli superiori non possono essere sovrascritti da quelli inferiori
- i prompt non contengono policy hardcoded (anti-pattern §25 punto 4)
- le policy vengono iniettate centralmente da `PolicyService`

---

## 14. Prompt management

### 14.1 Decisione

Langfuse è la fonte primaria dei prompt.

### 14.2 Fallback order

1. Langfuse (API call)
2. Bundled fallback file in `registries/prompts/defaults/`
3. Errore esplicito (no silent fallback)

### 14.3 NORMATIVE PSEUDOCODE

```python
# NORMATIVE PSEUDOCODE
async def resolve_prompt(prompt_id: str) -> str:
    try:
        return await langfuse_client.get_prompt(prompt_id)
    except LangfuseUnavailableError:
        if fallback_file_exists(prompt_id):
            logger.warning("langfuse_unavailable_using_fallback", prompt_id=prompt_id)
            return load_fallback_file(prompt_id)
        raise PromptNotResolvableError(prompt_id)
```

---

## 15. Chat architecture

### 15.1 NORMATIVE PSEUDOCODE — non streaming

```python
# NORMATIVE PSEUDOCODE
async def respond(
    session: AsyncSession,
    request: ChatRequest,
    context: RequestContext,
) -> ChatResponse:
    retrieval_result = await retrieval_service.retrieve(
        session=session,
        request=RetrievalRequest(
            query=request.message,
            space_ids=request.space_ids,
            conversation_id=request.conversation_id,
            retrieval_profile_id=request.retrieval_profile_id,
        ),
        context=context,
    )

    prompt = await prompt_service.build_prompt_stack(
        session=session,
        context=context,
        request=request,
        retrieval_result=retrieval_result,
    )

    input_transform = await pii_service.transform_input_if_needed(
        session=session,
        context=context,
        text=request.message,
    )

    llm_result = await llm_service.generate(
        prompt=prompt,
        transformed_user_text=input_transform.transformed_text,
        model_override=request.model_override,
        context=context,
    )

    output_transform = await pii_service.transform_output_if_needed(
        session=session,
        context=context,
        text=llm_result.content,
    )

    persisted = await conversation_service.persist_assistant_message(
        session=session,
        context=context,
        request=request,
        retrieval_result=retrieval_result,
        final_text=output_transform.transformed_text,
    )

    return ChatResponse(
        conversation_id=persisted.conversation_id,
        message_id=persisted.message_id,
        content=output_transform.transformed_text,
        citations=retrieval_result.citations,
        trace_id=context.trace_id,
    )
```

### 15.2 Streaming rules

Streaming MUST:

- emettere eventi tipizzati (`ChatStreamEvent`)
- propagare `trace_id` nell'evento `done`
- applicare PII secondo la modalità implementata (baseline conservativa)
- chiudere sempre con evento `done` o `error`
- persistere il messaggio completo dopo la fine dello stream

Streaming MUST NOT:
- emettere plain text non tipizzato
- lasciare la connection aperta senza heartbeat se il LLM è lento

---

## 16. PII specification

### 16.1 Modes

Vedere `PiiPolicy.mode` in §8.10.

### 16.2 Regole

MUST:
- trattare input e output separatamente
- trattare persistence, logs e traces separatamente
- usare chiavi di cifratura da secret store
- evitare raw PII in log/traces se `pii_policy.allow_raw_in_logs = False`

MUST NOT:
- applicare una trasformazione identica a tutti i sink senza distinzione
- assumere che streaming e batch abbiano le stesse garanzie
- salvare mapping chiari in Redis o Qdrant

### 16.3 Streaming baseline

La baseline MUST implementare PII su stream in modo conservativo:
- accumula token finché non ha un boundary sicuro (sentence o chunk)
- applica transform sul chunk completo
- emette token puliti

La specifica non impone un algoritmo token-by-token avanzato nella baseline.

---
