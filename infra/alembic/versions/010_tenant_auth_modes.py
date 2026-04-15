"""Add tenant auth modes and local auth users."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_table_if_role_exists


revision = "010_tenant_auth_modes"
down_revision = "009_llm_governance"
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
    op.add_column("tenants", sa.Column("auth_mode", sa.Text(), nullable=False, server_default=sa.text("'okta'")))
    op.add_column("tenants", sa.Column("okta_jwks_url", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("okta_issuer", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("okta_audience", sa.Text(), nullable=True))
    op.execute("ALTER TABLE tenants ALTER COLUMN okta_org_id DROP NOT NULL")
    op.create_check_constraint("ck_tenants_auth_mode", "tenants", "auth_mode IN ('okta','local')")

    op.create_table(
        "local_auth_users",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("tenant_id", "email", name="uq_local_auth_users_tenant_email"),
    )
    _configure_tenant_table("local_auth_users")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_local_auth_users ON local_auth_users")
    op.drop_table("local_auth_users")
    op.drop_constraint("ck_tenants_auth_mode", "tenants", type_="check")
    op.execute("ALTER TABLE tenants ALTER COLUMN okta_org_id SET NOT NULL")
    op.drop_column("tenants", "okta_audience")
    op.drop_column("tenants", "okta_issuer")
    op.drop_column("tenants", "okta_jwks_url")
    op.drop_column("tenants", "auth_mode")
