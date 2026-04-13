from __future__ import annotations

from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import settings


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"timeout": settings.postgres_connect_timeout_s},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_conn, _) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("SET app.current_tenant_id = ''")
    cursor.close()


async def set_tenant_rls(session: AsyncSession, tenant_id: UUID | str) -> None:
    tenant_value = str(UUID(str(tenant_id)))
    connection = await session.connection()
    await connection.exec_driver_sql(
        "SELECT set_config('app.current_tenant_id', $1, true)",
        (tenant_value,),
    )
