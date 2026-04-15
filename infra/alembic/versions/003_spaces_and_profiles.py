"""Add spaces and profile tables with tenant-aware defaults."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_table_if_role_exists


revision = "003_spaces_and_profiles"
down_revision = "002_identity_tables"
branch_labels = None
depends_on = None


def _configure_tenant_table(table_name: str, *, tenant_column: str = "tenant_id") -> None:
    alter_table_owner_if_role_exists(table_name, "aura_service")
    grant_on_table_if_role_exists(table_name, "aura_app", "SELECT, INSERT, UPDATE, DELETE")
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table_name} ON {table_name}
        USING ({tenant_column} = current_setting('app.current_tenant_id')::UUID)
        WITH CHECK ({tenant_column} = current_setting('app.current_tenant_id')::UUID)
        """
    )


def upgrade() -> None:
    op.create_table(
        "retrieval_profiles",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("rerank_top_k", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("score_threshold", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("dense_weight", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("sparse_weight", sa.Float(), nullable=False, server_default=sa.text("0.3")),
        sa.Column("reranker", sa.Text(), nullable=False, server_default=sa.text("'none'")),
        sa.Column("reranker_model", sa.Text(), nullable=True),
        sa.Column("query_rewrite_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("query_rewrite_model", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "reranker IN ('none','cross-encoder-local','litellm-rerank')",
            name="ck_retrieval_profiles_reranker",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_retrieval_profiles_tenant_name"),
    )
    op.create_table(
        "embedding_profiles",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("litellm_model", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False),
        sa.Column("splitter", sa.Text(), nullable=False, server_default=sa.text("'sentence'")),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default=sa.text("64")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("splitter IN ('sentence','token','semantic')", name="ck_embedding_profiles_splitter"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_embedding_profiles_tenant_name"),
    )
    op.create_table(
        "tone_profiles",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prompt_snippet", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("formality", sa.Text(), nullable=False, server_default=sa.text("'neutral'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("formality IN ('formal','neutral','casual')", name="ck_tone_profiles_formality"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tone_profiles_tenant_name"),
    )
    op.create_table(
        "knowledge_spaces",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("space_type", sa.Text(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("source_access_mode", sa.Text(), nullable=False, server_default=sa.text("'space_acl_only'")),
        sa.Column("embedding_profile_id", sa.UUID(), sa.ForeignKey("embedding_profiles.id"), nullable=False),
        sa.Column("retrieval_profile_id", sa.UUID(), sa.ForeignKey("retrieval_profiles.id"), nullable=False),
        sa.Column("pii_policy_id", sa.UUID(), nullable=True),
        sa.Column("tone_profile_id", sa.UUID(), sa.ForeignKey("tone_profiles.id"), nullable=True),
        sa.Column("system_instructions", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("space_type IN ('personal','team','enterprise')", name="ck_knowledge_spaces_space_type"),
        sa.CheckConstraint("visibility IN ('private','team','enterprise')", name="ck_knowledge_spaces_visibility"),
        sa.CheckConstraint(
            "source_access_mode IN ('space_acl_only','source_acl_enforced')",
            name="ck_knowledge_spaces_source_access_mode",
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_knowledge_spaces_status"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_knowledge_spaces_tenant_slug"),
    )
    op.create_table(
        "space_memberships",
        sa.Column("space_id", sa.UUID(), sa.ForeignKey("knowledge_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'reader'")),
        sa.CheckConstraint("role IN ('reader','editor','admin')", name="ck_space_memberships_role"),
        sa.PrimaryKeyConstraint("space_id", "user_id", name="pk_space_memberships"),
    )

    for table_name in ("retrieval_profiles", "embedding_profiles", "tone_profiles", "knowledge_spaces"):
        _configure_tenant_table(table_name)

    alter_table_owner_if_role_exists("space_memberships", "aura_service")
    grant_on_table_if_role_exists("space_memberships", "aura_app", "SELECT, INSERT, UPDATE, DELETE")
    op.execute("ALTER TABLE space_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE space_memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_space_memberships ON space_memberships
        USING (
            EXISTS (
                SELECT 1
                FROM knowledge_spaces
                WHERE knowledge_spaces.id = space_memberships.space_id
                  AND knowledge_spaces.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
            AND EXISTS (
                SELECT 1
                FROM users
                WHERE users.id = space_memberships.user_id
                  AND users.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM knowledge_spaces
                WHERE knowledge_spaces.id = space_memberships.space_id
                  AND knowledge_spaces.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
            AND EXISTS (
                SELECT 1
                FROM users
                WHERE users.id = space_memberships.user_id
                  AND users.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION seed_default_space_profiles()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO embedding_profiles (
                tenant_id, name, litellm_model, dimensions, chunk_size,
                chunk_overlap, splitter, batch_size, is_default
            )
            VALUES (
                NEW.id, 'default', 'text-embedding-3-small', 1536, 512,
                64, 'sentence', 64, TRUE
            )
            ON CONFLICT (tenant_id, name) DO NOTHING;

            INSERT INTO retrieval_profiles (
                tenant_id, name, top_k, rerank_top_k, score_threshold,
                dense_weight, sparse_weight, reranker, reranker_model,
                query_rewrite_enabled, query_rewrite_model, is_default
            )
            VALUES (
                NEW.id, 'default', 10, 5, 0.0,
                0.7, 0.3, 'none', NULL,
                FALSE, NULL, TRUE
            )
            ON CONFLICT (tenant_id, name) DO NOTHING;

            INSERT INTO tone_profiles (
                tenant_id, name, prompt_snippet, language, formality
            )
            VALUES (
                NEW.id, 'default', 'Rispondi con tono neutrale e professionale.', NULL, 'neutral'
            )
            ON CONFLICT (tenant_id, name) DO NOTHING;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_seed_default_space_profiles
        AFTER INSERT ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION seed_default_space_profiles()
        """
    )
    op.execute(
        """
        INSERT INTO embedding_profiles (
            tenant_id, name, litellm_model, dimensions, chunk_size,
            chunk_overlap, splitter, batch_size, is_default
        )
        SELECT
            tenants.id, 'default', 'text-embedding-3-small', 1536, 512,
            64, 'sentence', 64, TRUE
        FROM tenants
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO retrieval_profiles (
            tenant_id, name, top_k, rerank_top_k, score_threshold,
            dense_weight, sparse_weight, reranker, reranker_model,
            query_rewrite_enabled, query_rewrite_model, is_default
        )
        SELECT
            tenants.id, 'default', 10, 5, 0.0,
            0.7, 0.3, 'none', NULL,
            FALSE, NULL, TRUE
        FROM tenants
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO tone_profiles (
            tenant_id, name, prompt_snippet, language, formality
        )
        SELECT
            tenants.id, 'default', 'Rispondi con tono neutrale e professionale.', NULL, 'neutral'
        FROM tenants
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_seed_default_space_profiles ON tenants")
    op.execute("DROP FUNCTION IF EXISTS seed_default_space_profiles()")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_space_memberships ON space_memberships")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_knowledge_spaces ON knowledge_spaces")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_tone_profiles ON tone_profiles")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_embedding_profiles ON embedding_profiles")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_retrieval_profiles ON retrieval_profiles")
    op.drop_table("space_memberships")
    op.drop_table("knowledge_spaces")
    op.drop_table("tone_profiles")
    op.drop_table("embedding_profiles")
    op.drop_table("retrieval_profiles")
