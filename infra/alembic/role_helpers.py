from __future__ import annotations

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection


def role_exists(connection: Connection, role_name: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role_name)"),
            {"role_name": role_name},
        ).scalar()
    )


def set_role_if_exists(connection: Connection, role_name: str) -> None:
    if role_exists(connection, role_name):
        connection.exec_driver_sql(f"SET ROLE {role_name}")


def alter_table_owner_if_role_exists(table_name: str, role_name: str) -> None:
    bind = op.get_bind()
    if role_exists(bind, role_name):
        op.execute(f"ALTER TABLE {table_name} OWNER TO {role_name}")


def grant_on_schema_if_role_exists(schema_name: str, role_name: str, privileges: str) -> None:
    bind = op.get_bind()
    if role_exists(bind, role_name):
        op.execute(f"GRANT {privileges} ON SCHEMA {schema_name} TO {role_name}")


def grant_on_table_if_role_exists(table_name: str, role_name: str, privileges: str) -> None:
    bind = op.get_bind()
    if role_exists(bind, role_name):
        op.execute(f"GRANT {privileges} ON TABLE {table_name} TO {role_name}")
