"""Add policy tables for model, PII, and sandbox settings."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_table_if_role_exists


revision = "006_policy_tables"
down_revision = "005_chat_tables"
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
        "model_policies",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("default_model", sa.Text(), nullable=False),
        sa.Column("allowed_models", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default=sa.text("4096")),
        sa.Column("temperature", sa.Float(), nullable=False, server_default=sa.text("0.2")),
        sa.Column("context_window_limit", sa.Integer(), nullable=False, server_default=sa.text("128000")),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("rate_limit_tpd", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_model_policies_tenant_name"),
    )
    op.create_table(
        "pii_policies",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("entities_to_detect", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("score_threshold", sa.Float(), nullable=False, server_default=sa.text("0.7")),
        sa.Column("persist_mapping", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("mapping_ttl_days", sa.Integer(), nullable=True),
        sa.Column("allow_raw_in_logs", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("allow_raw_in_traces", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "mode IN ('off','detect_only','mask_inference_only','mask_persist_and_inference','pseudonymize_rehydratable')",
            name="ck_pii_policies_mode",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_pii_policies_tenant_name"),
    )
    op.create_table(
        "sandbox_policies",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("network_egress", sa.Text(), nullable=False, server_default=sa.text("'none'")),
        sa.Column("egress_allowlist", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("max_cpu_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("max_memory_mb", sa.Integer(), nullable=False, server_default=sa.text("512")),
        sa.Column("max_wall_time_s", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column(
            "writable_paths",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{\"/workspace\",\"/artifacts\"}'::text[]"),
        ),
        sa.Column("env_vars_allowed", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("network_egress IN ('none','allowlist')", name="ck_sandbox_policies_network_egress"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_sandbox_policies_tenant_name"),
    )

    for table_name in ("model_policies", "pii_policies", "sandbox_policies"):
        _configure_tenant_table(table_name)

    op.create_foreign_key(
        "fk_knowledge_spaces_pii_policy_id",
        "knowledge_spaces",
        "pii_policies",
        ["pii_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION seed_default_policies()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO model_policies (
                tenant_id, name, default_model, allowed_models, max_tokens,
                temperature, context_window_limit, is_default
            )
            VALUES (
                NEW.id, 'default', 'gpt-4o', ARRAY['gpt-4o'], 4096,
                0.2, 128000, TRUE
            )
            ON CONFLICT (tenant_id, name) DO NOTHING;

            INSERT INTO pii_policies (
                tenant_id, name, mode, entities_to_detect, score_threshold,
                persist_mapping, allow_raw_in_logs, allow_raw_in_traces, is_default
            )
            VALUES (
                NEW.id, 'default', 'off', '{}'::text[], 0.7,
                FALSE, FALSE, FALSE, TRUE
            )
            ON CONFLICT (tenant_id, name) DO NOTHING;

            INSERT INTO sandbox_policies (
                tenant_id, name, network_egress, egress_allowlist, max_cpu_seconds,
                max_memory_mb, max_wall_time_s, writable_paths, env_vars_allowed, is_default
            )
            VALUES (
                NEW.id, 'default', 'none', '{}'::text[], 60,
                512, 120, ARRAY['/workspace','/artifacts'], '{}'::text[], TRUE
            )
            ON CONFLICT (tenant_id, name) DO NOTHING;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_seed_default_policies
        AFTER INSERT ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION seed_default_policies()
        """
    )
    op.execute(
        """
        INSERT INTO model_policies (
            tenant_id, name, default_model, allowed_models, max_tokens,
            temperature, context_window_limit, is_default
        )
        SELECT
            tenants.id, 'default', 'gpt-4o', ARRAY['gpt-4o'], 4096,
            0.2, 128000, TRUE
        FROM tenants
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO pii_policies (
            tenant_id, name, mode, entities_to_detect, score_threshold,
            persist_mapping, allow_raw_in_logs, allow_raw_in_traces, is_default
        )
        SELECT
            tenants.id, 'default', 'off', '{}'::text[], 0.7,
            FALSE, FALSE, FALSE, TRUE
        FROM tenants
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO sandbox_policies (
            tenant_id, name, network_egress, egress_allowlist, max_cpu_seconds,
            max_memory_mb, max_wall_time_s, writable_paths, env_vars_allowed, is_default
        )
        SELECT
            tenants.id, 'default', 'none', '{}'::text[], 60,
            512, 120, ARRAY['/workspace','/artifacts'], '{}'::text[], TRUE
        FROM tenants
        ON CONFLICT (tenant_id, name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_seed_default_policies ON tenants")
    op.execute("DROP FUNCTION IF EXISTS seed_default_policies()")
    op.drop_constraint("fk_knowledge_spaces_pii_policy_id", "knowledge_spaces", type_="foreignkey")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_sandbox_policies ON sandbox_policies")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_pii_policies ON pii_policies")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_model_policies ON model_policies")
    op.drop_table("sandbox_policies")
    op.drop_table("pii_policies")
    op.drop_table("model_policies")
