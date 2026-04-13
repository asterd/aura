# AURA Spec — §38: Agent-in-Chat Integration
> Addendum v1.0 · Aprile 2026
> Estende §15 e §17 — definisce come gli agenti partecipano ai thread conversazionali

---

## 38. Agent-in-Chat Integration

### 38.1 Modello concettuale

Un agente può essere "attivato" in un thread conversazionale in tre modi:

| Modalità | Come si attiva | Comportamento |
|---|---|---|
| **Passive context** | `active_agent_ids` nella ChatRequest (già in §8.3) | L'agente contribuisce context al prompt stack, ma non esegue un run separato |
| **Explicit invocation** | `@agent-name` nel testo del messaggio | Il backend esegue un `AgentRunRequest` e ne incorpora l'output nella risposta |
| **Auto-invocation** | Manifest agente con `auto_invoke_on: [keyword, ...]` | Il backend determina se invocare l'agente in base al contenuto del messaggio |

---

### 38.2 Estensione ChatRequest

```python
# CONTRACT — estende §8.3 ChatRequest
class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str
    space_ids: list[UUID]
    additional_instructions: str | None = None
    active_agent_ids: list[UUID] = Field(default_factory=list)
    retrieval_profile_id: UUID | None = None
    model_override: str | None = None
    stream: bool = False
    # Nuovo campo:
    invoked_agents: list["AgentInvocation"] = Field(default_factory=list)

class AgentInvocation(BaseModel):
    agent_name: str
    agent_version: str | None = None     # None = latest published
    input_override: dict | None = None   # override dell'input derivato dal messaggio
```

Il frontend popola `invoked_agents` quando l'utente usa la sintassi `@agent-name` nel Composer.

---

### 38.3 AgentChatService

**Responsabilità precise:**
- Risolvere le invocazioni agente dal messaggio utente (parse `@mention` + `invoked_agents`).
- Costruire l'`AgentChatInput` per ciascun agente.
- Eseguire i run agente in parallelo via `asyncio.gather`.
- Consolidare i risultati nel prompt stack (livello `retrieved_context`) prima di chiamare `ChatService`.
- Allegare gli artifact dei run al messaggio assistant risultante.

**Pseudocodice normativo:**

```python
class AgentChatService:
    def __init__(
        self,
        agent_service: AgentService,
        chat_service: ChatService,
        retrieval_service: RetrievalService,
    ):
        ...

    async def respond(
        self,
        session: AsyncSession,
        ctx: RequestContext,
        request: ChatRequest,
        history: list[dict],
    ) -> ChatResponse | AsyncGenerator[ChatStreamEvent, None]:
        # 1. Parsing: estrarre @mention dal message
        mentioned_agents = self._parse_mentions(request.message)
        explicit_agents = request.invoked_agents or []
        all_invocations = self._merge_invocations(mentioned_agents, explicit_agents)

        # 2. Retrieval RAG (parallelo ai run agente)
        retrieval_task = asyncio.create_task(
            retrieval_service.retrieve(session, ctx, RetrievalRequest(
                query=request.message,
                space_ids=request.space_ids,
                conversation_id=request.conversation_id,
                retrieval_profile_id=request.retrieval_profile_id,
            ))
        )

        # 3. Agent runs (parallelo)
        agent_tasks = [
            asyncio.create_task(
                self._run_agent_for_chat(session, ctx, inv, request.message, history)
            )
            for inv in all_invocations
        ]

        # 4. Raccogliere risultati
        retrieval_result, *agent_results = await asyncio.gather(
            retrieval_task, *agent_tasks, return_exceptions=True
        )

        # 5. Costruire enhanced context
        enhanced_context = self._build_enhanced_context(
            retrieval_result, agent_results
        )

        # 6. Delegare a ChatService con context arricchito
        return await chat_service.respond_with_context(
            session=session,
            ctx=ctx,
            request=request,
            retrieval_result=enhanced_context,
            agent_run_ids=[r.run_id for r in agent_results if isinstance(r, AgentRunResult)],
        )

    async def _run_agent_for_chat(
        self,
        session: AsyncSession,
        ctx: RequestContext,
        invocation: AgentInvocation,
        user_message: str,
        history: list[dict],
    ) -> AgentRunResult:
        input_data = invocation.input_override or AgentChatInput(
            user_message=user_message,
            recent_messages=history[-10:],
            space_ids=[],  # resolved from thread context
        ).model_dump()

        return await agent_service.run_agent(
            session=session,
            ctx=ctx,
            request=AgentRunRequest(
                agent_name=invocation.agent_name,
                agent_version=invocation.agent_version,
                input=input_data,
                conversation_id=ctx.request_id,  # per tracciabilità
            )
        )
```

**Regole:**
- `AgentChatService` MUST NOT aprire sessioni DB — ricevere session iniettata.
- Se un agente fallisce (eccezione o `status="failed"`): loggare, includere nota di errore nel context, NON interrompere la risposta.
- Il run agente NON ha accesso alla history completa del thread — solo agli ultimi 10 messaggi passati come `recent_messages`.
- La risposta finale è sempre generata da `ChatService` — `AgentChatService` non genera mai testo direttamente.

---

### 38.4 Formato context arricchito

L'output degli agenti viene iniettato nel prompt stack al livello `retrieved_context` (posizione 7 di 8 — §13) con questo formato:

```
[AGENT: {agent_name} v{version}]
{output_text}
---
```

Se più agenti contribuiscono, i loro output sono separati da `---` e precedono il context RAG.

Se un agente fallisce, il suo slot nel context è:

```
[AGENT: {agent_name} — UNAVAILABLE: {error_message}]
```

---

### 38.5 Streaming con agenti

Quando `stream: true` e ci sono agenti invocati:

1. Prima emettere un evento `agent_running` per ciascun agente (nuovo tipo evento).
2. Eseguire i run agente in parallelo (non in streaming — attendere il completamento).
3. Una volta completati tutti i run, iniziare lo streaming della risposta ChatService.

**Nuovo evento SSE:**

```python
# CONTRACT — aggiunge a ChatStreamEvent (§8.3)
class ChatStreamEventAgentRunning(BaseModel):
    type: Literal["agent_running"]
    agent_name: str
    run_id: UUID

class ChatStreamEventAgentDone(BaseModel):
    type: Literal["agent_done"]
    agent_name: str
    run_id: UUID
    status: Literal["succeeded", "failed"]
    artifacts: list[str] = Field(default_factory=list)

# ChatStreamEvent aggiornato
ChatStreamEvent = (
    ChatStreamEventToken
    | ChatStreamEventCitation
    | ChatStreamEventDone
    | ChatStreamEventError
    | ChatStreamEventAgentRunning  # nuovo
    | ChatStreamEventAgentDone     # nuovo
)
```

Il frontend mostra un indicatore "running" per ciascun agente tra l'invio del messaggio e l'inizio del token streaming.

---

### 38.6 Auto-invocation (opzionale, Fase 7+)

Se un agente ha `auto_invoke_on` nel manifest, il backend può decidere di invocarlo automaticamente:

```yaml
# Campo aggiuntivo nel manifest (opzionale)
auto_invoke_on:
  keywords: ["contratto", "contract", "NDA", "SLA"]
  space_ids: ["contracts-space-uuid"]   # solo per messaggi con questi spaces attivi
  confidence_threshold: 0.8             # soglia rilevanza (futura, non implementata in v1)
```

**Regole auto-invocation:**
- In v1: match solo keyword (case-insensitive, stem matching non richiesto).
- `auto_invoke_on.space_ids` non vuoto: l'auto-invocation avviene solo se uno di quegli spaces è nella `space_ids` della request corrente.
- L'utente può disabilitare l'auto-invocation per un thread specifico tramite impostazione thread (futura).
- L'auto-invocation è subordinata a `active_agent_ids`: se l'agente non è nella lista degli agenti attivi del thread, non viene auto-invocato.

---

### 38.7 Multi-agent session

Più agenti possono essere attivi contemporaneamente in un thread. Regole:

- Non c'è comunicazione diretta tra agenti in una stessa request — sono eseguiti in parallelo senza visibilità reciproca degli output.
- La comunicazione inter-agente è supportata solo via tipo `orchestrator` (§17.1) con sub-agent delegation esplicita.
- Il numero massimo di agenti invocabili in una singola request è **5** (configurabile per tenant tramite `ModelPolicy.max_agents_per_request` — campo da aggiungere al contratto).

---

### 38.8 Schema DB aggiuntivo

```sql
-- Tracking invocazioni agente per messaggio
CREATE TABLE message_agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    message_id UUID NOT NULL REFERENCES messages(id),
    agent_run_id UUID NOT NULL REFERENCES agent_runs(id),
    agent_name TEXT NOT NULL,
    invocation_mode TEXT NOT NULL CHECK (invocation_mode IN ('explicit', 'mention', 'auto')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON message_agent_runs (tenant_id, conversation_id);
CREATE INDEX ON message_agent_runs (message_id);
```

---

### 38.9 Endpoint aggiornato

L'endpoint `/api/v1/chat/stream` e `/api/v1/chat/respond` gestiscono automaticamente le invocazioni agente tramite `AgentChatService`. Non sono necessari endpoint separati.

Il routing è:

```python
# In router /chat
@router.post("/stream")
async def chat_stream(request: ChatRequest, ...):
    if request.invoked_agents or _has_mentions(request.message):
        # usa AgentChatService
        return await agent_chat_service.respond(session, ctx, request, history)
    else:
        # percorso normale senza agenti
        return await chat_service.stream(session, ctx, request)
```

**REGOLA**: questa logica di routing sta nel router (thin router — §1.3), non nel service. Il service non decide se usare agenti o no — riceve istruzioni esplicite.
