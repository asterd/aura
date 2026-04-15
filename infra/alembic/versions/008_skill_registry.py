"""Add skill registry tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_table_if_role_exists


revision = "008_skill_registry"
down_revision = "007_agent_registry"
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
        "skill_packages",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_skill_packages_tenant_name"),
    )
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_package_id", sa.UUID(), sa.ForeignKey("skill_packages.id"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("entrypoint", sa.Text(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_ref", sa.Text(), nullable=False),
        sa.Column("artifact_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("sandbox_policy_id", sa.UUID(), sa.ForeignKey("sandbox_policies.id"), nullable=True),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("status IN ('draft','validated','published','deprecated')", name="ck_skill_versions_status"),
        sa.UniqueConstraint("skill_package_id", "version", name="uq_skill_versions_package_version"),
    )
    for table_name in ("skill_packages", "skill_versions"):
        _configure_tenant_table(table_name)


def downgrade() -> None:
    for table_name in ("skill_versions", "skill_packages"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
        op.drop_table(table_name)
