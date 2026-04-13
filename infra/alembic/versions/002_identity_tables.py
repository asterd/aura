"""Add identity tables with tenant RLS."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "002_identity_tables"
down_revision = "001_initial_tenants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("okta_sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("tenant_id", "okta_sub", name="uq_users_tenant_okta_sub"),
    )
    op.create_table(
        "groups",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_groups_tenant_external_id"),
    )
    op.create_table(
        "user_group_memberships",
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.UUID(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "group_id", name="pk_user_group_memberships"),
    )

    for table_name in ("users", "groups", "user_group_memberships"):
        op.execute(f"ALTER TABLE {table_name} OWNER TO aura_service")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table_name} TO aura_app")
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY tenant_isolation_users ON users
        USING (tenant_id = current_setting('app.current_tenant_id')::UUID)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::UUID)
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_groups ON groups
        USING (tenant_id = current_setting('app.current_tenant_id')::UUID)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::UUID)
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_user_group_memberships ON user_group_memberships
        USING (
            EXISTS (
                SELECT 1
                FROM users
                WHERE users.id = user_group_memberships.user_id
                  AND users.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
            AND EXISTS (
                SELECT 1
                FROM groups
                WHERE groups.id = user_group_memberships.group_id
                  AND groups.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM users
                WHERE users.id = user_group_memberships.user_id
                  AND users.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
            AND EXISTS (
                SELECT 1
                FROM groups
                WHERE groups.id = user_group_memberships.group_id
                  AND groups.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_user_group_memberships ON user_group_memberships")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_groups ON groups")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_users ON users")
    op.drop_table("user_group_memberships")
    op.drop_table("groups")
    op.drop_table("users")
