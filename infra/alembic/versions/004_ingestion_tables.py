"""Add datasource and document ingestion tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from infra.alembic.role_helpers import alter_table_owner_if_role_exists, grant_on_table_if_role_exists


revision = "004_ingestion_tables"
down_revision = "003_spaces_and_profiles"
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
        "datasources",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("space_id", sa.UUID(), sa.ForeignKey("knowledge_spaces.id"), nullable=False),
        sa.Column("connector_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("credentials_ref", sa.Text(), nullable=False),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.Text(), nullable=True),
        sa.Column("stale_threshold_s", sa.Integer(), nullable=False, server_default=sa.text("86400")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "last_sync_status IN ('ok','partial','failed','auth_error','stale')",
            name="ck_datasources_last_sync_status",
        ),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("space_id", sa.UUID(), sa.ForeignKey("knowledge_spaces.id"), nullable=False),
        sa.Column("datasource_id", sa.UUID(), sa.ForeignKey("datasources.id"), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'discovered'")),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('discovered','fetched','parsed','canonicalized','indexed','active','deleted','error')",
            name="ck_documents_status",
        ),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("version_hash", sa.Text(), nullable=False),
        sa.Column("s3_canonical_ref", sa.Text(), nullable=True),
        sa.Column("s3_original_ref", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("indexed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("document_id", "version_hash", name="uq_document_versions_hash"),
    )

    for table_name in ("datasources", "documents", "document_versions"):
        _configure_tenant_table(table_name)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_document_versions ON document_versions")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_documents ON documents")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_datasources ON datasources")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("datasources")
