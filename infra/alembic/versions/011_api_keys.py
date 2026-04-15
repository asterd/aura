"""add api_keys table

Revision ID: 011
Revises: 010
Create Date: 2026-04-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_table_if_role_exists


revision = "011_api_keys"
down_revision = "010_tenant_auth_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    alter_table_owner_if_role_exists("api_keys", "aura_service")
    grant_on_table_if_role_exists("api_keys", "aura_app", "SELECT, INSERT, UPDATE, DELETE")
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE api_keys FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY api_keys_tenant_isolation ON api_keys
        USING (tenant_id = current_setting('app.current_tenant_id')::UUID)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::UUID)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS api_keys_tenant_isolation ON api_keys")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
