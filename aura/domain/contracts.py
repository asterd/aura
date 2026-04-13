from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field
from typing import Literal


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


class JobPayload(BaseModel):
    tenant_id: UUID
    job_key: str
    requested_by_user_id: UUID | None = None
    trace_id: str | None = None
