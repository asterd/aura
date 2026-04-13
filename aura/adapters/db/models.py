from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
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
    pii_policy_id: Mapped[UUID | None] = mapped_column(nullable=True)
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
