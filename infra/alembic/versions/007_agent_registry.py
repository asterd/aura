"""Add agent registry, runs, triggers, and message agent run tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "007_agent_registry"
down_revision = "006_policy_tables"
branch_labels = None
depends_on = None


def _configure_tenant_table(table_name: str, *, tenant_column: str = "tenant_id") -> None:
    op.execute(f"ALTER TABLE {table_name} OWNER TO aura_service")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table_name} TO aura_app")
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
        "agent_packages",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_agent_packages_tenant_name"),
    )
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_package_id", sa.UUID(), sa.ForeignKey("agent_packages.id"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("agent_type", sa.Text(), nullable=False),
        sa.Column("entrypoint", sa.Text(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_ref", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("model_policy_id", sa.UUID(), sa.ForeignKey("model_policies.id"), nullable=True),
        sa.Column("pii_policy_id", sa.UUID(), sa.ForeignKey("pii_policies.id"), nullable=True),
        sa.Column("sandbox_policy_id", sa.UUID(), sa.ForeignKey("sandbox_policies.id"), nullable=True),
        sa.Column("max_budget_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "agent_type IN ('single','orchestrator','triggered','autonomous')",
            name="ck_agent_versions_agent_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft','validated','published','deprecated')",
            name="ck_agent_versions_status",
        ),
        sa.UniqueConstraint("agent_package_id", "version", name="uq_agent_versions_package_version"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), sa.ForeignKey("agent_versions.id"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.UUID(), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_ref", sa.Text(), nullable=True),
        sa.Column("output_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("artifact_refs", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running','succeeded','failed')", name="ck_agent_runs_status"),
    )
    op.create_table(
        "agent_trigger_registrations",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), sa.ForeignKey("agent_versions.id"), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("runs_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("trigger_type IN ('cron', 'event')", name="ck_agent_trigger_registrations_type"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'deregistered')",
            name="ck_agent_trigger_registrations_status",
        ),
    )
    op.create_table(
        "message_agent_runs",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("conversation_id", sa.UUID(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("message_id", sa.UUID(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("agent_run_id", sa.UUID(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("invocation_mode", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "invocation_mode IN ('explicit','mention','auto')",
            name="ck_message_agent_runs_invocation_mode",
        ),
    )

    for table_name in (
        "agent_packages",
        "agent_versions",
        "agent_runs",
        "agent_trigger_registrations",
        "message_agent_runs",
    ):
        _configure_tenant_table(table_name)

    op.create_index(
        "ix_agent_trigger_registrations_tenant_type_status",
        "agent_trigger_registrations",
        ["tenant_id", "trigger_type", "status"],
    )
    op.create_index(
        "ix_agent_trigger_registrations_agent_version_id",
        "agent_trigger_registrations",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_message_agent_runs_tenant_conversation",
        "message_agent_runs",
        ["tenant_id", "conversation_id"],
    )
    op.create_index("ix_message_agent_runs_message_id", "message_agent_runs", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_agent_runs_message_id", table_name="message_agent_runs")
    op.drop_index("ix_message_agent_runs_tenant_conversation", table_name="message_agent_runs")
    op.drop_index("ix_agent_trigger_registrations_agent_version_id", table_name="agent_trigger_registrations")
    op.drop_index("ix_agent_trigger_registrations_tenant_type_status", table_name="agent_trigger_registrations")
    for table_name in (
        "message_agent_runs",
        "agent_trigger_registrations",
        "agent_runs",
        "agent_versions",
        "agent_packages",
    ):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
        op.drop_table(table_name)
