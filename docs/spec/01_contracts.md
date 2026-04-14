# AURA Spec — §8: Core Contracts
> Source: AURA Backbone v4.3 · Sezione §8
> ⚠️ QUESTI CONTRATTI NON VANNO MAI MODIFICATI INLINE.
> Implementarli in `aura/domain/contracts.py` e importarli da lì.

## 8. Core contracts

Questa sezione contiene i contratti minimi obbligatori.

### 8.1 Identity contracts

```python
# CONTRACT
class UserIdentity(BaseModel):
    user_id: UUID
    tenant_id: UUID
    okta_sub: str
    email: EmailStr
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    group_ids: list[UUID] = Field(default_factory=list)
    is_service_identity: bool = False
```

```python
# CONTRACT
class RequestContext(BaseModel):
    request_id: str
    trace_id: str
    tenant_id: UUID
    identity: UserIdentity
    now_utc: datetime
```

### 8.2 Retrieval contracts

```python
# CONTRACT
class RetrievalRequest(BaseModel):
    query: str
    space_ids: list[UUID]
    conversation_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    query_rewrite_enabled: bool | None = None
```

```python
# CONTRACT
class Citation(BaseModel):
    citation_id: str
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    title: str
    source_system: str
    source_path: str
    source_url: str | None = None
    page_or_section: str | None = None
    score: float
    snippet: str
```

```python
# CONTRACT
class RetrievalResult(BaseModel):
    query: str
    context_blocks: list[str]
    citations: list[Citation]
    retrieval_profile_id: UUID
    total_candidates: int
    used_candidates: int
```

### 8.3 Chat contracts

```python
# CONTRACT
class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str
    space_ids: list[UUID]
    additional_instructions: str | None = None
    active_agent_ids: list[UUID] = Field(default_factory=list)
    retrieval_profile_id: UUID | None = None
    model_override: str | None = None
    stream: bool = False
```

```python
# CONTRACT
class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    content: str
    citations: list[Citation]
    trace_id: str
```

```python
# CONTRACT
class ChatStreamEventToken(BaseModel):
    type: Literal["token"]
    content: str

class ChatStreamEventCitation(BaseModel):
    type: Literal["citation"]
    citation: Citation

class ChatStreamEventDone(BaseModel):
    type: Literal["done"]
    message_id: UUID
    trace_id: str

class ChatStreamEventError(BaseModel):
    type: Literal["error"]
    code: str
    message: str

ChatStreamEvent = ChatStreamEventToken | ChatStreamEventCitation | ChatStreamEventDone | ChatStreamEventError
```

### 8.4 Connector contracts

```python
# CONTRACT
class NormalizedACL(BaseModel):
    mode: Literal["space_acl_only", "source_acl_enforced"]
    allow_users: list[str] = Field(default_factory=list)
    allow_groups: list[UUID] = Field(default_factory=list)
    deny_users: list[str] = Field(default_factory=list)
    deny_groups: list[UUID] = Field(default_factory=list)
    inherited: bool = True
```

```python
# CONTRACT
class DocumentMetadata(BaseModel):
    title: str
    source_path: str
    source_url: str | None = None
    content_type: str
    language: str | None = None
    classification: str | None = None
    tags: list[str] = Field(default_factory=list)
    modified_at: datetime | None = None
```

```python
# CONTRACT
class LoadedDocument(BaseModel):
    external_id: str
    metadata: DocumentMetadata
    raw_text: str | None = None
    raw_bytes_ref: str | None = None  # S3 key se il file è già stato caricato
    acl: NormalizedACL | None = None
    is_deleted: bool = False
```

### 8.5 Agent contracts

```python
# CONTRACT
class AgentRunRequest(BaseModel):
    agent_name: str
    agent_version: str | None = None
    input: dict
    conversation_id: UUID | None = None
```

```python
# CONTRACT
class AgentRunResult(BaseModel):
    run_id: UUID
    agent_name: str
    agent_version: str
    status: Literal["succeeded", "failed"]
    output_data: dict | None = None
    output_text: str | None = None
    trace_id: str
    artifacts: list[str] = Field(default_factory=list)
    error_message: str | None = None
```

```python
# CONTRACT
@dataclass
class AgentDeps:
    identity: UserIdentity
    model_policy: "ModelPolicy"
    pii_policy: "PiiPolicy | None"
    allowed_spaces: list[UUID]
    allowed_tools: list[str]
    litellm_base_url: str
    litellm_virtual_key: str
    knowledge_service: "KnowledgeService"
    artifact_writer: "ArtifactWriter"
    resolve_system_prompt: Callable[[str], str]
```

### 8.6 PII contracts

```python
# CONTRACT
class DetectedEntity(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    value_preview: str | None = None
```

```python
# CONTRACT
class PiiTransformResult(BaseModel):
    mode: str
    transformed_text: str
    detected_entities: list[DetectedEntity]
    mapping_refs: list[str] = Field(default_factory=list)
    had_transformations: bool
```

### 8.7 Job contracts

```python
# CONTRACT
class JobPayload(BaseModel):
    tenant_id: UUID
    job_key: str
    requested_by_user_id: UUID | None = None
    trace_id: str | None = None
```

### 8.8 Profile e policy domain contracts

Questi modelli corrispondono a record DB per tenant. Sono entità Pydantic usate a runtime, non configurazione statica.

```python
# CONTRACT
class EmbeddingProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    litellm_model: str           # e.g. "text-embedding-3-small" via LiteLLM
    dimensions: int              # e.g. 1536
    chunk_size: int              # token o caratteri secondo splitter
    chunk_overlap: int
    splitter: Literal["sentence", "token", "semantic"]
    batch_size: int = 64
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
```

```python
# CONTRACT
class RetrievalProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    top_k: int = 10              # candidati da retrieval
    rerank_top_k: int = 5        # candidati dopo reranking
    score_threshold: float = 0.0
    dense_weight: float = 0.7
    sparse_weight: float = 0.3
    reranker: Literal["none", "cross-encoder-local", "litellm-rerank"] = "none"
    reranker_model: str | None = None  # obbligatorio se reranker != "none"
    query_rewrite_enabled: bool = False
    query_rewrite_model: str | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
```

```python
# CONTRACT
class ToneProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    prompt_snippet: str          # iniettato nel prompt stack come tenant_tone_prompt
    language: str | None = None  # ISO 639-1
    formality: Literal["formal", "neutral", "casual"] = "neutral"
    created_at: datetime
    updated_at: datetime
```

### 8.9 ModelPolicy contract

```python
# CONTRACT
class ModelPolicy(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    default_model: str           # e.g. "gpt-4o", "claude-3-5-sonnet", "mistral-large"
    allowed_models: list[str]    # whitelist; vuota = solo default_model
    max_tokens: int = 4096
    temperature: float = 0.2
    context_window_limit: int = 128_000
    rate_limit_rpm: int | None = None
    rate_limit_tpd: int | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
```

**Regola**: se `model_override` nella ChatRequest non è in `allowed_models`, la request viene rifiutata con HTTP 422.

### 8.10 PiiPolicy contract

```python
# CONTRACT
class PiiMode(str, Enum):
    off = "off"
    detect_only = "detect_only"
    mask_inference_only = "mask_inference_only"
    mask_persist_and_inference = "mask_persist_and_inference"
    pseudonymize_rehydratable = "pseudonymize_rehydratable"

class PiiPolicy(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    mode: PiiMode
    entities_to_detect: list[str] = Field(default_factory=list)  # vuota = tutte
    score_threshold: float = 0.7
    persist_mapping: bool = False       # True solo per pseudonymize_rehydratable
    mapping_ttl_days: int | None = None
    allow_raw_in_logs: bool = False
    allow_raw_in_traces: bool = False
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
```

**Tabella normativa modalità PII** (invariante):

| Mode | Input to LLM | Persisted text | Output to user | Raw recoverable |
|---|---|---|---|---|
| off | raw | raw | raw | yes |
| detect_only | raw | raw | raw | yes |
| mask_inference_only | masked | raw | raw | yes |
| mask_persist_and_inference | masked | masked | masked | no |
| pseudonymize_rehydratable | pseudonymized | pseudonymized + mapping refs | policy-defined | yes via mapping |

### 8.11 SandboxPolicy contract

```python
# CONTRACT
class NetworkEgressMode(str, Enum):
    none = "none"
    allowlist = "allowlist"

class SandboxPolicy(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    network_egress: NetworkEgressMode = NetworkEgressMode.none
    egress_allowlist: list[str] = Field(default_factory=list)  # FQDN o CIDR
    max_cpu_seconds: int = 60
    max_memory_mb: int = 512
    max_wall_time_s: int = 120
    writable_paths: list[str] = Field(default_factory=lambda: ["/workspace", "/artifacts"])
    env_vars_allowed: list[str] = Field(default_factory=list)
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
```

### 8.12 LLM governance contracts

```python
# CONTRACT
class LlmProvider(BaseModel):
    id: UUID
    provider_key: Literal[
        "openai", "anthropic", "azure_openai", "google_vertex",
        "bedrock", "mistral", "custom_openai_compatible"
    ]
    display_name: str
    description: str | None = None
    base_url: str | None = None
    supports_chat: bool = True
    supports_embeddings: bool = False
    supports_reasoning: bool = False
    supports_tools: bool = False
    status: Literal["active", "disabled", "deprecated"] = "active"


class TenantProviderCredential(BaseModel):
    id: UUID
    tenant_id: UUID
    provider_id: UUID
    name: str
    secret_ref: str
    endpoint_override: str | None = None
    is_default: bool = False
    status: Literal["active", "disabled"] = "active"


class TenantModelConfig(BaseModel):
    id: UUID
    tenant_id: UUID
    provider_id: UUID
    credential_id: UUID
    task_type: Literal["chat", "embedding", "rerank"]
    model_name: str
    model_alias: str | None = None
    litellm_model_name: str | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    max_requests_per_minute: int | None = None
    max_concurrent_requests: int | None = None
    status: Literal["enabled", "disabled"] = "enabled"
```

### 8.13 Cost governance contracts

```python
# CONTRACT
class BudgetScope(str, Enum):
    tenant = "tenant"
    user = "user"
    provider = "provider"
    space = "space"


class BudgetWindow(str, Enum):
    daily = "daily"
    monthly = "monthly"


class BudgetAction(str, Enum):
    block = "block"
    warn_only = "warn_only"


class CostBudget(BaseModel):
    id: UUID
    tenant_id: UUID
    scope_type: BudgetScope
    scope_ref: str
    provider_id: UUID | None = None
    model_name: str | None = None
    window: BudgetWindow
    soft_limit_usd: float | None = None
    hard_limit_usd: float
    action_on_hard_limit: BudgetAction = BudgetAction.block
    is_active: bool = True


class LlmUsageRecord(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None = None
    provider_id: UUID
    model_name: str
    task_type: Literal["chat", "embedding", "rerank", "agent"]
    space_id: UUID | None = None
    conversation_id: UUID | None = None
    agent_run_id: UUID | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    measured_at: datetime
```

### 8.12 ConnectorCredentials contract

```python
# CONTRACT
class CredentialType(str, Enum):
    oauth2_bearer = "oauth2_bearer"
    api_key = "api_key"
    service_account_json = "service_account_json"
    client_credentials = "client_credentials"
    basic = "basic"

class ConnectorCredentials(BaseModel):
    credential_type: CredentialType
    secret_ref: str         # chiave nel secret store — mai il valore segreto
    scopes: list[str] = Field(default_factory=list)
    tenant_domain: str | None = None   # e.g. "contoso.sharepoint.com"
    extra: dict = Field(default_factory=dict)  # parametri non-secret extra

class ResolvedCredentials(BaseModel):
    """Oggetto in-memory post-resoluzione da secret store. MAI persistere."""
    credential_type: CredentialType
    token_or_key: str       # il valore reale, solo in memoria
    scopes: list[str]
    tenant_domain: str | None
    extra: dict
```

**Regola**: `ResolvedCredentials` non viene mai serializzato, loggato o passato a un job ARQ. Viene creato e usato nell'esecuzione corrente, poi garbage-collected.

---
