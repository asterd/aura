# AURA Spec — §21: API Surface and Schemas
> Source: AURA Backbone v4.3

## 21. API surface and schemas

Questa sezione definisce i core endpoints obbligatori.

### 21.1 `POST /api/v1/chat/retrieve`

```python
class RetrieveApiRequest(BaseModel):
    query: str
    space_ids: list[UUID]
    conversation_id: UUID | None = None
    retrieval_profile_id: UUID | None = None

class RetrieveApiResponse(BaseModel):
    result: RetrievalResult
    trace_id: str
```

### 21.2 `POST /api/v1/chat/respond`

```python
class RespondApiRequest(ChatRequest):
    stream: Literal[False] = False

class RespondApiResponse(ChatResponse):
    pass
```

### 21.3 `POST /api/v1/chat/stream`

```python
class StreamApiRequest(ChatRequest):
    stream: Literal[True] = True
# Response: SSE di ChatStreamEvent*
```

### 21.4 `POST /api/v1/agents/{name}/run`

```python
class AgentRunApiRequest(BaseModel):
    input: dict
    version: str | None = None
    conversation_id: UUID | None = None

class AgentRunApiResponse(AgentRunResult):
    pass
```

### 21.5 `POST /api/v1/datasources/upload`

Multipart: `space_id`, `file`

```python
class UploadDatasourceResponse(BaseModel):
    datasource_id: UUID
    document_id: UUID
    job_id: UUID
```

### 21.6 `POST /api/v1/admin/agents/upload`

Multipart: `manifest.yaml`, `agent_code.zip`

```python
class AgentUploadResponse(BaseModel):
    agent_package_id: UUID
    agent_version_id: UUID
    status: Literal["draft", "validated", "failed"]
```

### 21.7 `GET /api/v1/health`

```python
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, Literal["ok", "degraded", "down"]]
    # components: postgres, redis, qdrant, litellm, langfuse, s3
```

### 21.8 `GET /api/v1/me`

```python
class MeResponse(BaseModel):
    identity: UserIdentity
    spaces: list[UUID]
    active_policies: dict[str, UUID]  # model_policy_id, pii_policy_id, etc.
```

### 21.9 `GET /api/v1/admin/llm/providers`

Lista provider supportati dal backbone.

### 21.10 `POST /api/v1/admin/llm/credentials`

Registra una credential tenant-level tramite `secret_ref`.

### 21.11 `GET /api/v1/admin/llm/credentials`

Lista credential censite per il tenant corrente.

### 21.12 `POST /api/v1/admin/llm/models`

Abilita un modello tenant-level per uno specifico task type.

### 21.13 `GET /api/v1/admin/llm/models`

Lista modelli abilitati per il tenant corrente.

### 21.14 `POST /api/v1/admin/llm/budgets`

Crea o aggiorna un budget di costo per tenant, utente, provider o progetto/spazio.

### 21.15 `GET /api/v1/admin/llm/budgets`

Lista budget attivi per il tenant corrente.

### 21.16 `GET /api/v1/admin/llm/usage`

Restituisce usage aggregato e costo per tenant/provider/modello/scopo.

### 21.17 `POST /api/v1/admin/tenants/provision`

Crea un tenant con `auth_mode=okta` o `auth_mode=local`. Richiede `X-Bootstrap-Token`.

### 21.18 `POST /api/v1/auth/local/login`

Autentica un utente di un tenant `local` e restituisce un bearer JWT firmato internamente.

### 21.19 `GET /api/v1/admin/tenants/current`

Restituisce configurazione e auth mode del tenant corrente.

### 21.20 `PATCH /api/v1/admin/tenants/current/auth`

Aggiorna `display_name` e la configurazione auth del tenant corrente.

Supporta:

- switch `local -> okta`
- switch `okta -> local`
- bootstrap admin locale quando necessario

### 21.21 `GET /api/v1/admin/tenants/local-users`

Lista utenti locali registrati per il tenant corrente.

### 21.22 `POST /api/v1/admin/tenants/local-users`

Crea un nuovo utente locale tenant-scoped.

### 21.23 `PATCH /api/v1/admin/tenants/local-users/{user_id}`

Aggiorna ruoli, display name, password o stato attivo di un utente locale.

### 21.24 `GET /api/v1/admin/llm/runtime-key`

Restituisce lo stato della tenant runtime key LiteLLM sincronizzata da AURA.

### 21.25 `POST /api/v1/admin/llm/runtime-key/sync`

Forza una risincronizzazione della tenant runtime key sulle API admin di LiteLLM.

---
