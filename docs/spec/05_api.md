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

---
