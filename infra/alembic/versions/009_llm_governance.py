"""Add LLM provider governance and cost management tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "009_llm_governance"
down_revision = "008_skill_registry"
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
        "llm_providers",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider_key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("supports_chat", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("supports_embeddings", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("supports_reasoning", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("base_url_hint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("status IN ('active','disabled','deprecated')", name="ck_llm_providers_status"),
        sa.UniqueConstraint("provider_key", name="uq_llm_providers_provider_key"),
    )
    op.execute("ALTER TABLE llm_providers OWNER TO aura_service")
    op.execute("GRANT SELECT ON TABLE llm_providers TO aura_app")

    op.create_table(
        "tenant_provider_credentials",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider_id", sa.UUID(), sa.ForeignKey("llm_providers.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("secret_ref", sa.Text(), nullable=False),
        sa.Column("endpoint_override", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_tenant_provider_credentials_status"),
        sa.UniqueConstraint("tenant_id", "provider_id", "name", name="uq_tenant_provider_credentials_name"),
    )

    op.create_table(
        "tenant_model_configs",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider_id", sa.UUID(), sa.ForeignKey("llm_providers.id"), nullable=False),
        sa.Column("credential_id", sa.UUID(), sa.ForeignKey("tenant_provider_credentials.id"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("litellm_model_name", sa.Text(), nullable=True),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("concurrency_limit", sa.Integer(), nullable=True),
        sa.Column("input_cost_per_1k", sa.Numeric(10, 6), nullable=True),
        sa.Column("output_cost_per_1k", sa.Numeric(10, 6), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'enabled'")),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("task_type IN ('chat','embedding','rerank','agent')", name="ck_tenant_model_configs_task_type"),
        sa.CheckConstraint("status IN ('enabled','disabled')", name="ck_tenant_model_configs_status"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_id",
            "credential_id",
            "task_type",
            "model_name",
            name="uq_tenant_model_configs_binding",
        ),
    )

    op.create_table(
        "cost_budgets",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_ref", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.UUID(), sa.ForeignKey("llm_providers.id"), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("budget_window", sa.Text(), nullable=False),
        sa.Column("soft_limit_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("hard_limit_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("action_on_hard_limit", sa.Text(), nullable=False, server_default=sa.text("'block'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("scope_type IN ('tenant','user','provider','space')", name="ck_cost_budgets_scope_type"),
        sa.CheckConstraint("budget_window IN ('daily','monthly')", name="ck_cost_budgets_window"),
        sa.CheckConstraint("action_on_hard_limit IN ('block','warn_only')", name="ck_cost_budgets_action"),
        sa.UniqueConstraint(
            "tenant_id",
            "scope_type",
            "scope_ref",
            "provider_id",
            "model_name",
            "budget_window",
            name="uq_cost_budgets_scope",
        ),
    )

    op.create_table(
        "llm_usage_records",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("provider_id", sa.UUID(), sa.ForeignKey("llm_providers.id"), nullable=False),
        sa.Column("credential_id", sa.UUID(), sa.ForeignKey("tenant_provider_credentials.id"), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("space_id", sa.UUID(), sa.ForeignKey("knowledge_spaces.id"), nullable=True),
        sa.Column("conversation_id", sa.UUID(), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("agent_run_id", sa.UUID(), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("measured_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.CheckConstraint("task_type IN ('chat','embedding','rerank','agent')", name="ck_llm_usage_records_task_type"),
    )

    for table_name in ("tenant_provider_credentials", "tenant_model_configs", "cost_budgets", "llm_usage_records"):
        _configure_tenant_table(table_name)

    op.create_index("ix_tenant_model_configs_tenant_task", "tenant_model_configs", ["tenant_id", "task_type", "status"])
    op.create_index("ix_cost_budgets_tenant_scope", "cost_budgets", ["tenant_id", "scope_type", "scope_ref"])
    op.create_index("ix_llm_usage_records_tenant_measured_at", "llm_usage_records", ["tenant_id", "measured_at"])
    op.create_index("ix_llm_usage_records_tenant_provider_model", "llm_usage_records", ["tenant_id", "provider_id", "model_name"])

    providers = [
        ("openai", "OpenAI", "OpenAI public API", True, True, True, True, "https://api.openai.com/v1"),
        ("anthropic", "Anthropic", "Anthropic Messages API", True, False, True, True, "https://api.anthropic.com"),
        ("azure_openai", "Azure OpenAI", "Azure OpenAI deployments", True, True, True, True, None),
        ("google_vertex", "Google Vertex AI", "Vertex AI Generative APIs", True, True, True, True, None),
        ("bedrock", "Amazon Bedrock", "AWS Bedrock managed models", True, True, True, True, None),
        ("mistral", "Mistral", "Mistral public API", True, True, True, True, "https://api.mistral.ai/v1"),
        ("custom_openai_compatible", "Custom OpenAI Compatible", "OpenAI-compatible self-hosted endpoints", True, True, False, True, None),
    ]
    for provider_key, display_name, description, supports_chat, supports_embeddings, supports_reasoning, supports_tools, base_url_hint in providers:
        op.execute(
            sa.text(
                """
                INSERT INTO llm_providers (
                    provider_key, display_name, description,
                    supports_chat, supports_embeddings, supports_reasoning, supports_tools,
                    base_url_hint, status
                )
                VALUES (
                    :provider_key, :display_name, :description,
                    :supports_chat, :supports_embeddings, :supports_reasoning, :supports_tools,
                    :base_url_hint, 'active'
                )
                ON CONFLICT (provider_key) DO NOTHING
                """
            ).bindparams(
                provider_key=provider_key,
                display_name=display_name,
                description=description,
                supports_chat=supports_chat,
                supports_embeddings=supports_embeddings,
                supports_reasoning=supports_reasoning,
                supports_tools=supports_tools,
                base_url_hint=base_url_hint,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_records_tenant_provider_model", table_name="llm_usage_records")
    op.drop_index("ix_llm_usage_records_tenant_measured_at", table_name="llm_usage_records")
    op.drop_index("ix_cost_budgets_tenant_scope", table_name="cost_budgets")
    op.drop_index("ix_tenant_model_configs_tenant_task", table_name="tenant_model_configs")
    for table_name in ("llm_usage_records", "cost_budgets", "tenant_model_configs", "tenant_provider_credentials"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
        op.drop_table(table_name)
    op.drop_table("llm_providers")
