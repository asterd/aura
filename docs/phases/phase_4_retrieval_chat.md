# Fase 4 — Retrieval e Chat
> AURA Backbone v4.3 · Fase 4 di 9
> **Prerequisito**: Fase 3 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.2: RetrievalRequest/Result/Citation; §8.3: ChatRequest/Response/StreamEvent)
docs/spec/02_services.md    (§7.2: RetrievalService; §7.3: ChatService; §13: prompt stack; §14: prompt mgmt; §15: chat arch)
docs/spec/03_knowledge.md   (§12: retrieval architecture, filter builder)
docs/spec/07_db_schema.md   (§31.3: conversations, messages, message_citations)
```

---

## Obiettivo

`POST /api/v1/chat/respond` funzionante end-to-end con retrieval ibrido, prompt stack corretto, citations restituite. SSE streaming funzionante. Conversation persistita.

---

## Tasks obbligatori

### 4.1 — Migration tabelle
Da `docs/spec/07_db_schema.md §31.3`: `conversations`, `messages`, `message_citations`.
RLS su tutte.

### 4.2 — RetrievalService
`aura/services/retrieval.py` — implementare il pseudocodice normativo da `docs/spec/02_services.md §12.1` **esattamente**:
1. Validate request + space authorization
2. Resolve RetrievalProfile (da DB, fallback a default tenant)
3. Build Qdrant filter (tenant_id + space_ids + ACL se source_acl_enforced)
4. Hybrid search (dense + sparse con RRF)
5. Reranking (se profile.reranker != "none")
6. Context assembly
7. Citation normalization → lista `Citation`
8. Return `RetrievalResult`

**INVARIANTI** (da `docs/spec/02_services.md §12.2`):
- NON persiste messages
- NON chiama LiteLLM per generation
- NON emette SSE

### 4.3 — Filter builder
`aura/adapters/qdrant/filter_builder.py`:
```python
def build_retrieval_filter(
    tenant_id: UUID,
    space_ids: list[UUID],
    identity: UserIdentity,
    acl_mode: str,
) -> models.Filter:
    # MUST filtrare per tenant_id (sempre)
    # MUST filtrare per space_id (sempre)
    # Se source_acl_enforced: MUST filtrare acl_allow_users/groups, MUST NOT acl_deny_users
```

### 4.4 — PromptService
`aura/services/prompt_service.py`:
- `resolve_prompt(prompt_id)` → string (con fallback Langfuse → file, pseudocodice da §14.3)
- `build_prompt_stack(session, context, request, retrieval_result)` → list[Message]
  Stack obbligatorio **nell'ordine esatto** da `docs/spec/02_services.md §13`

### 4.5 — ChatService non-streaming
`aura/services/chat.py` — implementare `respond()` seguendo il pseudocodice normativo da `docs/spec/02_services.md §15.1` **esattamente**.
In questa fase PII transform è un no-op (sarà implementato in Fase 5).

### 4.6 — ChatService streaming
`respond_stream()` → `AsyncGenerator[ChatStreamEvent, None]`
- Emettere `ChatStreamEventToken` per ogni token
- Emettere `ChatStreamEventCitation` per le citations
- Chiudere sempre con `ChatStreamEventDone` o `ChatStreamEventError`
- Persistere il messaggio completo DOPO la fine dello stream

### 4.7 — API endpoints
```
POST /api/v1/chat/retrieve   → RetrieveApiResponse
POST /api/v1/chat/respond    → RespondApiResponse
POST /api/v1/chat/stream     → SSE (text/event-stream)
```

---

## Acceptance criteria (GATE)

```python
async def test_chat_respond_with_citations():
    # Prerequisito: doc indicizzato con contenuto "La policy ferie è 25 giorni"
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    r = await client.post("/api/v1/chat/respond", json={
        "message": "Quanti giorni di ferie ho?",
        "space_ids": [str(SPACE_ID)],
        "stream": False
    }, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["content"]          # risposta non vuota
    assert len(body["citations"]) > 0  # almeno una citation
    assert body["trace_id"]

async def test_chat_stream_events_typed():
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    async with client.stream("POST", "/api/v1/chat/stream", json={
        "message": "test", "space_ids": [str(SPACE_ID)], "stream": True
    }, headers=auth(token)) as r:
        events = [parse_sse(line) async for line in r.aiter_lines() if line.startswith("data:")]
    types = [e["type"] for e in events]
    assert "token" in types
    assert types[-1] in ("done", "error")  # sempre chiuso correttamente

async def test_retrieval_acl_respected():
    """Un utente non membro dello space non riceve documenti da quello space."""
    token_non_member = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_NOT_MEMBER)
    r = await client.post("/api/v1/chat/retrieve", json={
        "query": "test",
        "space_ids": [str(PRIVATE_SPACE_ID)]
    }, headers=auth(token_non_member))
    assert r.status_code == 403

async def test_conversation_persisted():
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    r = await client.post("/api/v1/chat/respond", json={
        "message": "ciao", "space_ids": [str(SPACE_ID)]
    }, headers=auth(token))
    conv_id = r.json()["conversation_id"]
    msg_id = r.json()["message_id"]
    # Verifica nel DB
    msg = await get_message(msg_id)
    assert msg.conversation_id == UUID(conv_id)
    assert msg.role == "assistant"
```

---

## Note per Claude Code

- Il prompt stack deve rispettare ESATTAMENTE l'ordine di §13. Non riordinare i livelli.
- Le citations restituite in `ChatResponse` sono quelle del `RetrievalResult`, non generate dall'LLM.
- Per il fallback Langfuse → file: i file di fallback sono in `registries/prompts/defaults/{prompt_id}.txt`. Creare almeno `platform_system_prompt.txt` con un placeholder.
- In questa fase `pii_service.transform_*_if_needed` può essere uno stub che restituisce il testo invariato — la PII reale arriva in Fase 5.
