from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import UserIdentity


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    identity: UserIdentity | None = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, identity.tenant_id)
            request.state.db = session
            request.state.tenant_id = identity.tenant_id
            yield session


async def get_unscoped_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
