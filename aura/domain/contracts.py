from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Literal
from uuid import UUID
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field


class UserIdentity(BaseModel):
    user_id: UUID
    tenant_id: UUID
    okta_sub: str
    email: EmailStr
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    group_ids: list[UUID] = Field(default_factory=list)
    is_service_identity: bool = False


class RequestContext(BaseModel):
    request_id: str
    trace_id: str
    tenant_id: UUID
    identity: UserIdentity
    now_utc: datetime


class EmbeddingProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    litellm_model: str
    dimensions: int
    chunk_size: int
    chunk_overlap: int
    splitter: Literal["sentence", "token", "semantic"]
    batch_size: int = 64
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class RetrievalProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    top_k: int = 10
    rerank_top_k: int = 5
    score_threshold: float = 0.0
    dense_weight: float = 0.7
    sparse_weight: float = 0.3
    reranker: Literal["none", "cross-encoder-local", "litellm-rerank"] = "none"
    reranker_model: str | None = None
    query_rewrite_enabled: bool = False
    query_rewrite_model: str | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class ToneProfile(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    prompt_snippet: str
    language: str | None = None
    formality: Literal["formal", "neutral", "casual"] = "neutral"
    created_at: datetime
    updated_at: datetime


class ModelPolicy(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    default_model: str
    allowed_models: list[str]
    max_tokens: int = 4096
    temperature: float = 0.2
    context_window_limit: int = 128_000
    rate_limit_rpm: int | None = None
    rate_limit_tpd: int | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


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
    entities_to_detect: list[str] = Field(default_factory=list)
    score_threshold: float = 0.7
    persist_mapping: bool = False
    mapping_ttl_days: int | None = None
    allow_raw_in_logs: bool = False
    allow_raw_in_traces: bool = False
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class NetworkEgressMode(str, Enum):
    none = "none"
    allowlist = "allowlist"


class SandboxPolicy(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    network_egress: NetworkEgressMode = NetworkEgressMode.none
    egress_allowlist: list[str] = Field(default_factory=list)
    max_cpu_seconds: int = 60
    max_memory_mb: int = 512
    max_wall_time_s: int = 120
    writable_paths: list[str] = Field(default_factory=lambda: ["/workspace", "/artifacts"])
    env_vars_allowed: list[str] = Field(default_factory=list)
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class KnowledgeSpace(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    space_type: Literal["personal", "team", "enterprise"]
    visibility: Literal["private", "team", "enterprise"]
    source_access_mode: Literal["space_acl_only", "source_acl_enforced"]
    embedding_profile_id: UUID
    retrieval_profile_id: UUID
    pii_policy_id: UUID | None = None
    tone_profile_id: UUID | None = None
    system_instructions: str | None = None
    status: Literal["active", "archived"]
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class NormalizedACL(BaseModel):
    mode: Literal["space_acl_only", "source_acl_enforced"]
    allow_users: list[str] = Field(default_factory=list)
    allow_groups: list[UUID] = Field(default_factory=list)
    deny_users: list[str] = Field(default_factory=list)
    deny_groups: list[UUID] = Field(default_factory=list)
    inherited: bool = True


class DocumentMetadata(BaseModel):
    title: str
    source_path: str
    source_url: str | None = None
    content_type: str
    language: str | None = None
    classification: str | None = None
    tags: list[str] = Field(default_factory=list)
    modified_at: datetime | None = None


class LoadedDocument(BaseModel):
    external_id: str
    metadata: DocumentMetadata
    raw_text: str | None = None
    raw_bytes_ref: str | None = None
    acl: NormalizedACL | None = None
    is_deleted: bool = False


class CredentialType(str, Enum):
    oauth2_bearer = "oauth2_bearer"
    api_key = "api_key"
    service_account_json = "service_account_json"
    client_credentials = "client_credentials"
    basic = "basic"


class ConnectorCredentials(BaseModel):
    credential_type: CredentialType
    secret_ref: str
    scopes: list[str] = Field(default_factory=list)
    tenant_domain: str | None = None
    extra: dict = Field(default_factory=dict)


class ResolvedCredentials(BaseModel):
    credential_type: CredentialType
    token_or_key: str
    scopes: list[str] = Field(default_factory=list)
    tenant_domain: str | None = None
    extra: dict = Field(default_factory=dict)


class McpServerCapabilities(BaseModel):
    tools: list[str] = Field(default_factory=list)
    tenant_id: UUID
    identity_sub: str
    server_version: str


class McpToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict = Field(default_factory=dict)


class McpToolResult(BaseModel):
    tool_name: str
    content: list[dict] = Field(default_factory=list)
    is_error: bool = False
    error_message: str | None = None


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


class RetrievalRequest(BaseModel):
    query: str
    space_ids: list[UUID]
    conversation_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    query_rewrite_enabled: bool | None = None


class RetrievalResult(BaseModel):
    query: str
    context_blocks: list[str]
    citations: list[Citation]
    retrieval_profile_id: UUID
    total_candidates: int
    used_candidates: int


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str
    space_ids: list[UUID]
    additional_instructions: str | None = None
    active_agent_ids: list[UUID] = Field(default_factory=list)
    retrieval_profile_id: UUID | None = None
    model_override: str | None = None
    stream: bool = False
    invoked_agents: list["AgentInvocation"] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    content: str
    citations: list[Citation]
    trace_id: str


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


ChatStreamEvent = (
    ChatStreamEventToken
    | ChatStreamEventCitation
    | ChatStreamEventDone
    | ChatStreamEventError
    | ChatStreamEventAgentRunning
    | ChatStreamEventAgentDone
)


class AgentRunRequest(BaseModel):
    run_id: UUID | None = None
    agent_name: str
    agent_version: str | None = None
    input: dict
    conversation_id: UUID | None = None


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


@dataclass
class AgentDeps:
    identity: UserIdentity
    model_policy: "ModelPolicy"
    pii_policy: "PiiPolicy | None"
    allowed_spaces: list[UUID]
    allowed_tools: list[str]
    litellm_base_url: str
    litellm_virtual_key: str
    knowledge_service: Any
    artifact_writer: Any
    resolve_system_prompt: Callable[[str], str]
    mcp_adapters: dict[str, "McpBridgeAdapter"] = field(default_factory=dict)


class AgentInvocation(BaseModel):
    agent_name: str
    agent_version: str | None = None
    input_override: dict | None = None


class AgentChatInput(BaseModel):
    user_message: str
    recent_messages: list[dict] = Field(default_factory=list)
    space_ids: list[UUID] = Field(default_factory=list)


class CronTrigger(BaseModel):
    type: Literal["cron"] = "cron"
    cron_expression: str
    max_runs: int | None = None
    run_as_service_identity: bool = True


class EventTrigger(BaseModel):
    type: Literal["event"] = "event"
    event_type: Literal[
        "document.ingested",
        "document.updated",
        "document.deleted",
        "space.member_added",
        "space.member_removed",
        "webhook.inbound",
    ]
    space_ids: list[UUID] = Field(default_factory=list)
    filter_tags: list[str] = Field(default_factory=list)
    webhook_secret_ref: str | None = None


AgentTrigger = CronTrigger | EventTrigger


class InternalEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    event_type: str
    source_entity_id: UUID | None = None
    source_space_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime


class DetectedEntity(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    value_preview: str | None = None


class PiiTransformResult(BaseModel):
    mode: str
    transformed_text: str
    detected_entities: list[DetectedEntity]
    mapping_refs: list[str] = Field(default_factory=list)
    had_transformations: bool


class JobPayload(BaseModel):
    tenant_id: UUID
    job_key: str
    requested_by_user_id: UUID | None = None
    trace_id: str | None = None


class SandboxInput(BaseModel):
    skill_version_id: UUID
    artifact_ref: str
    entrypoint: str
    input_obj: dict = Field(default_factory=dict)
    profile: SandboxPolicy
    trace_id: str


class SandboxArtifact(BaseModel):
    name: str
    content_type: str
    size_bytes: int
    s3_ref: str


class SandboxResult(BaseModel):
    status: Literal["succeeded", "failed", "timeout"]
    output: dict | None = None
    error_message: str | None = None
    artifacts: list[SandboxArtifact] = Field(default_factory=list)
    wall_time_s: float
    exit_code: int | None = None


class IdentitySyncResult(BaseModel):
    tenant_id: UUID
    users_seen: int
    users_updated: int
    groups_seen: int
    groups_updated: int
    unmapped_users: int
    partial_failures: int
    completed_at: datetime


ChatRequest.model_rebuild()
