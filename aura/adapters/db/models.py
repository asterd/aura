from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Numeric,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    okta_org_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "okta_sub", name="uq_users_tenant_okta_sub"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    okta_sub: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_groups_tenant_external_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserGroupMembership(Base):
    __tablename__ = "user_group_memberships"
    __table_args__ = (PrimaryKeyConstraint("user_id", "group_id", name="pk_user_group_memberships"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)


class EmbeddingProfile(Base):
    __tablename__ = "embedding_profiles"
    __table_args__ = (
        CheckConstraint("splitter IN ('sentence','token','semantic')", name="ck_embedding_profiles_splitter"),
        UniqueConstraint("tenant_id", "name", name="uq_embedding_profiles_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    litellm_model: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False)
    splitter: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'sentence'"))
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("64"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RetrievalProfile(Base):
    __tablename__ = "retrieval_profiles"
    __table_args__ = (
        CheckConstraint(
            "reranker IN ('none','cross-encoder-local','litellm-rerank')",
            name="ck_retrieval_profiles_reranker",
        ),
        UniqueConstraint("tenant_id", "name", name="uq_retrieval_profiles_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    rerank_top_k: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    score_threshold: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    dense_weight: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.7"))
    sparse_weight: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.3"))
    reranker: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'none'"))
    reranker_model: Mapped[str | None] = mapped_column(Text)
    query_rewrite_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    query_rewrite_model: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ToneProfile(Base):
    __tablename__ = "tone_profiles"
    __table_args__ = (
        CheckConstraint("formality IN ('formal','neutral','casual')", name="ck_tone_profiles_formality"),
        UniqueConstraint("tenant_id", "name", name="uq_tone_profiles_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text)
    formality: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'neutral'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ModelPolicy(Base):
    __tablename__ = "model_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_model_policies_tenant_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_model: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_models: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4096"))
    temperature: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.2"))
    context_window_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("128000"))
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer)
    rate_limit_tpd: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PiiPolicy(Base):
    __tablename__ = "pii_policies"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('off','detect_only','mask_inference_only','mask_persist_and_inference','pseudonymize_rehydratable')",
            name="ck_pii_policies_mode",
        ),
        UniqueConstraint("tenant_id", "name", name="uq_pii_policies_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    entities_to_detect: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    score_threshold: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.7"))
    persist_mapping: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    mapping_ttl_days: Mapped[int | None] = mapped_column(Integer)
    allow_raw_in_logs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    allow_raw_in_traces: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SandboxPolicy(Base):
    __tablename__ = "sandbox_policies"
    __table_args__ = (
        CheckConstraint("network_egress IN ('none','allowlist')", name="ck_sandbox_policies_network_egress"),
        UniqueConstraint("tenant_id", "name", name="uq_sandbox_policies_tenant_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    network_egress: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'none'"))
    egress_allowlist: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    max_cpu_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    max_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("512"))
    max_wall_time_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    writable_paths: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{\"/workspace\",\"/artifacts\"}'::text[]"),
    )
    env_vars_allowed: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KnowledgeSpace(Base):
    __tablename__ = "knowledge_spaces"
    __table_args__ = (
        CheckConstraint("space_type IN ('personal','team','enterprise')", name="ck_knowledge_spaces_space_type"),
        CheckConstraint("visibility IN ('private','team','enterprise')", name="ck_knowledge_spaces_visibility"),
        CheckConstraint(
            "source_access_mode IN ('space_acl_only','source_acl_enforced')",
            name="ck_knowledge_spaces_source_access_mode",
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_knowledge_spaces_status"),
        UniqueConstraint("tenant_id", "slug", name="uq_knowledge_spaces_tenant_slug"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    space_type: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    source_access_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'space_acl_only'"))
    embedding_profile_id: Mapped[UUID] = mapped_column(ForeignKey("embedding_profiles.id"), nullable=False)
    retrieval_profile_id: Mapped[UUID] = mapped_column(ForeignKey("retrieval_profiles.id"), nullable=False)
    pii_policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("pii_policies.id"), nullable=True)
    tone_profile_id: Mapped[UUID | None] = mapped_column(ForeignKey("tone_profiles.id"), nullable=True)
    system_instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SpaceMembership(Base):
    __tablename__ = "space_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('reader','editor','admin')", name="ck_space_memberships_role"),
        PrimaryKeyConstraint("space_id", "user_id", name="pk_space_memberships"),
    )

    space_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_spaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'reader'"))


class Datasource(Base):
    __tablename__ = "datasources"
    __table_args__ = (
        CheckConstraint(
            "last_sync_status IN ('ok','partial','failed','auth_error','stale')",
            name="ck_datasources_last_sync_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    space_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_spaces.id"), nullable=False)
    connector_type: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    credentials_ref: Mapped[str] = mapped_column(Text, nullable=False)
    sync_cursor: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(Text)
    stale_threshold_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("86400"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('discovered','fetched','parsed','canonicalized','indexed','active','deleted','error')",
            name="ck_documents_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    space_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_spaces.id"), nullable=False)
    datasource_id: Mapped[UUID | None] = mapped_column(ForeignKey("datasources.id"))
    external_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'discovered'"))
    current_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_hash", name="uq_document_versions_hash"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    version_hash: Mapped[str] = mapped_column(Text, nullable=False)
    s3_canonical_ref: Mapped[str | None] = mapped_column(Text)
    s3_original_ref: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    space_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]"))
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    citation_id: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AgentPackage(Base):
    __tablename__ = "agent_packages"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_agent_packages_tenant_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class SkillPackage(Base):
    __tablename__ = "skill_packages"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_skill_packages_tenant_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        CheckConstraint(
            "agent_type IN ('single','orchestrator','triggered','autonomous')",
            name="ck_agent_versions_agent_type",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published','deprecated')",
            name="ck_agent_versions_status",
        ),
        UniqueConstraint("agent_package_id", "version", name="uq_agent_versions_package_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    agent_package_id: Mapped[UUID] = mapped_column(ForeignKey("agent_packages.id"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    entrypoint: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_ref: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    model_policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("model_policies.id"))
    pii_policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("pii_policies.id"))
    sandbox_policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("sandbox_policies.id"))
    max_budget_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        CheckConstraint("status IN ('draft','validated','published','deprecated')", name="ck_skill_versions_status"),
        UniqueConstraint("skill_package_id", "version", name="uq_skill_versions_package_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    skill_package_id: Mapped[UUID] = mapped_column(ForeignKey("skill_packages.id"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    entrypoint: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_ref: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    sandbox_policy_id: Mapped[UUID | None] = mapped_column(ForeignKey("sandbox_policies.id"))
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (CheckConstraint("status IN ('running','succeeded','failed')", name="ck_agent_runs_status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    agent_version_id: Mapped[UUID] = mapped_column(ForeignKey("agent_versions.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_ref: Mapped[str | None] = mapped_column(Text)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    output_text: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    artifact_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentTriggerRegistration(Base):
    __tablename__ = "agent_trigger_registrations"
    __table_args__ = (
        CheckConstraint("trigger_type IN ('cron', 'event')", name="ck_agent_trigger_registrations_type"),
        CheckConstraint(
            "status IN ('active', 'paused', 'deregistered')",
            name="ck_agent_trigger_registrations_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    agent_version_id: Mapped[UUID] = mapped_column(ForeignKey("agent_versions.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    runs_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MessageAgentRun(Base):
    __tablename__ = "message_agent_runs"
    __table_args__ = (
        CheckConstraint(
            "invocation_mode IN ('explicit', 'mention', 'auto')",
            name="ck_message_agent_runs_invocation_mode",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), nullable=False)
    agent_run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    invocation_mode: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
