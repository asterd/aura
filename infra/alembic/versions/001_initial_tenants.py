"""Initial tenants table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_schema_if_role_exists, grant_on_table_if_role_exists


revision = "001_initial_tenants"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("okta_org_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_tenants_status"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.UniqueConstraint("okta_org_id", name="uq_tenants_okta_org_id"),
    )
    alter_table_owner_if_role_exists("tenants", "aura_service")
    grant_on_schema_if_role_exists("public", "aura_app", "USAGE")
    grant_on_table_if_role_exists("tenants", "aura_app", "SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    op.drop_table("tenants")
