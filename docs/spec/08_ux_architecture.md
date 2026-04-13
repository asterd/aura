# AURA Spec — §35: UX Architecture
> Addendum v1.0 · Aprile 2026
> Copre: conversational threading, streaming UX, composer, sidebar, artifact viewer

---

## 35. UX Architecture

### 35.1 Principi

1. **API-first** — ogni interazione UI passa per le API AURA già specificate (§21). La UI non è mai source of truth.
2. **Optimistic UI** — messaggi mostrati immediatamente, riconciliati all'arrivo dell'evento SSE `done`.
3. **State machine esplicita** — ogni thread ha uno stato finito; nessun "limbo" silenzioso.
4. **Zero PII in localStorage/sessionStorage** — la UI non persiste dati sensibili localmente.

---

### 35.2 Conversation Threading

#### Modello concettuale

```
Thread
├── id: UUID
├── title: string | null          # generato dal primo messaggio (≤ 60 char)
├── space_ids: UUID[]             # spaces attivi per questo thread
├── active_agent_ids: UUID[]      # agenti attivi (per invocazione contestuale)
├── retrieval_profile_id: UUID | null
├── created_at: datetime
└── messages: Message[]
```

```
Message
├── id: UUID
├── role: "user" | "assistant" | "agent"
├── content: string
├── citations: Citation[]
├── artifacts: ArtifactRef[]
├── agent_run_id: UUID | null     # se generato da un agente
├── status: "streaming" | "done" | "error"
└── created_at: datetime
```

#### Regole threading

- Ogni `ChatRequest` con `conversation_id` già esistente estende il thread corrente.
- Il frontend invia sempre `conversation_id`; la prima request ne riceve uno nuovo dal backend.
- Non esiste branch/fork di thread nella v1. Aggiungere in fase futura.
- Il titolo del thread viene generato backend-side al primo scambio (job ARQ, non bloccante).

---

### 35.3 Streaming UX

Il frontend consuma il flusso SSE di `ChatStreamEvent` (§8.3) e lo renderizza incrementalmente.

**State machine di un messaggio assistant in streaming:**

```
PENDING → STREAMING → DONE
                   ↘ ERROR
```

Regole:
- All'evento `token`: appendere il contenuto al buffer, renderizzare con debounce (max 50ms).
- All'evento `citation`: aggiungere la citation alla lista, non interrompere il rendering del testo.
- All'evento `done`: finalizzare il messaggio, salvare `message_id` e `trace_id`, aggiornare lo stato a `DONE`.
- All'evento `error`: mostrare inline error nel bubble del messaggio, stato `ERROR`. Non rimuovere il contenuto parziale già renderizzato.
- Se la connessione SSE cade prima di `done`: retry automatico una volta con lo stesso `conversation_id`, poi stato `ERROR`.

---

### 35.4 Composer

Il Composer è il campo di input principale. Supporta:

| Feature | Sintassi | Behaviour |
|---|---|---|
| Testo libero | — | Chat standard via `/chat/stream` |
| Invocazione agente | `@agent-name` | Aggiunge l'agente ad `active_agent_ids` e passa la query all'`AgentChatService` (§35.8) |
| Mention spazio | `#space-name` | Aggiunge lo space a `space_ids` della request corrente |
| Upload file | drag-and-drop / icona | Upload verso `/datasources/upload`, poi conferma di ingestione |
| Comandi slash | `/help`, `/clear`, `/agents` | Gestiti client-side, non inviati al backend |

**Regole Composer:**
- `@agent-name` apre un dropdown con agenti disponibili (fetch da `/api/v1/agents` — endpoint da aggiungere in §35.9).
- `#space-name` apre un dropdown con spaces a cui l'utente ha accesso.
- Il Composer non consente l'invio se un messaggio è in stato `STREAMING`.
- Max dimensione testo: 32.000 caratteri (validazione client-side, rifiuto backend con HTTP 422 se superato).

---

### 35.5 Sidebar

La sidebar organizza la navigazione principale:

```
Sidebar
├── New Chat (CTA primario)
├── Thread History
│   ├── Today
│   ├── Last 7 days
│   └── Older
├── Spaces
│   └── [Lista spaces con accesso read+]
├── Agents
│   └── [Lista agenti disponibili per il tenant]
└── Settings (link)
```

**Regole sidebar:**
- La lista thread viene paginata (cursor-based, page size 20).
- La lista spaces viene caricata all'avvio e refreshata ogni 5 minuti (o su focus tab).
- La lista agenti include solo agenti con status `published`.
- Il titolo del thread è truncato a 50 char con ellipsis.

---

### 35.6 Artifact Viewer

Gli artifact prodotti da agenti e skill (§19) vengono renderizzati inline nel thread.

```
ArtifactRef
├── artifact_id: string      # path S3 o ID
├── artifact_type: ArtifactType
├── label: string | null
└── created_at: datetime
```

```
ArtifactType = "markdown" | "code" | "csv" | "json" | "pdf_preview" | "image" | "unknown"
```

| Tipo | Renderer |
|---|---|
| `markdown` | Renderer markdown con syntax highlighting |
| `code` | Code block con copy button e language badge |
| `csv` | Tabella HTML scrollabile, max 500 righe renderizzate |
| `json` | JSON tree collassabile |
| `pdf_preview` | Link di download + anteprima prima pagina se < 5MB |
| `image` | `<img>` con lazy loading |
| `unknown` | Link di download |

**Regole artifact viewer:**
- Gli artifact NON vengono incorporati nel body del messaggio come base64. Sempre via URL firmato S3.
- Gli URL firmati hanno TTL 15 minuti. Il frontend re-fetches l'URL firmato on-demand se scaduto.
- Ogni artifact mostra `label` o filename come titolo, e la data di creazione.

---

### 35.7 Stato globale UI (Zustand — pattern consigliato)

```typescript
// Store shape (non normativo — implementazione a discrezione del frontend)
interface AuraStore {
  // Thread
  threads: Thread[]
  activeThreadId: string | null
  threadMessages: Record<string, Message[]>

  // Streaming
  streamingMessageId: string | null
  streamBuffer: string

  // Spaces & Agents (cache)
  availableSpaces: Space[]
  availableAgents: AgentSummary[]

  // Active context per thread
  activeSpaceIds: Record<string, string[]>
  activeAgentIds: Record<string, string[]>
}
```

Regole:
- Lo store NON persiste in localStorage. Alla ricarica, reidratare dal backend.
- `streamBuffer` viene svuotato all'evento `done`.
- `threadMessages` viene popolato on-demand (lazy load per thread ID).

---

### 35.8 AgentChatService (backend)

Questo service coordina l'esecuzione di agenti dentro un thread conversazionale.

**Responsabilità:**
- Ricevere una `ChatRequest` con `active_agent_ids` non vuoto.
- Per ciascun agente attivo, costruire un `AgentRunRequest` con `input` derivato dal messaggio utente e dalla history recente del thread (max 10 messaggi).
- Eseguire gli agenti in parallelo (se più di uno, con `asyncio.gather`).
- Consolidare i risultati degli agenti e il retrieval RAG in un unico prompt stack.
- Produrre la risposta finale via `ChatService` con il contesto arricchito.

**Contratto input agente da chat:**

```python
# CONTRACT — non modificare inline
class AgentChatInput(BaseModel):
    user_message: str
    thread_summary: str | None = None   # riassunto ultimi N messaggi
    recent_messages: list[dict]         # [{"role": "user"|"assistant", "content": str}]
    space_ids: list[UUID]
```

**Regole:**
- Se un agente fallisce, il suo errore viene incluso nel contesto come nota, non interrompe la risposta.
- Il `output_text` dell'agente viene iniettato nel prompt stack al livello `retrieved_context` (§13).
- Gli artifact prodotti dall'agente vengono allegati al messaggio assistant finale.
- `AgentChatService` DEVE loggare `agent_run_id` come attributo OTel del trace corrente.

---

### 35.9 Endpoint aggiuntivi richiesti da UX

Questi endpoint vanno aggiunti alla specifica API (§21):

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/v1/conversations` | GET | Lista thread paginata (cursor) per l'utente corrente |
| `/api/v1/conversations/{id}` | GET | Thread completo con messaggi |
| `/api/v1/conversations/{id}` | DELETE | Soft-delete del thread |
| `/api/v1/agents` | GET | Lista agenti `published` disponibili per il tenant |
| `/api/v1/conversations/{id}/messages` | GET | Messaggi paginati del thread |

**Schema risposta `/api/v1/conversations`:**

```python
class ConversationSummary(BaseModel):
    conversation_id: UUID
    title: str | None
    last_message_at: datetime
    message_count: int
    active_space_ids: list[UUID]

class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    next_cursor: str | None
```

---

### 35.10 Sequenza fase UI (dopo Fase 4)

La UI viene sviluppata in parallelo alle fasi backend a partire dalla Fase 3, seguendo questa progressione:

| Sub-fase UI | Dipende da | Deliverable |
|---|---|---|
| UI-A: Shell | Fase 1 (/me) | Login, sidebar vuota, new chat |
| UI-B: Chat Base | Fase 4 (/chat/stream) | Composer, thread, streaming bubble |
| UI-C: Spaces | Fase 2 (spaces CRUD) | Selector spaces nel Composer, #mention |
| UI-D: Upload | Fase 3 (upload) | Drag-and-drop nel Composer |
| UI-E: Agents | Fase 7 (agent registry) | @mention agenti, artifact viewer |
| UI-F: Policies | Fase 5 (policies) | Badge PII, indicator policy attiva |
