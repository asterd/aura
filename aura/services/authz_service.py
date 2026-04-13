from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aura.domain.contracts import RequestContext, UserIdentity


class AuthzService:
    async def ensure_can_run_agent(self, *, session: AsyncSession, identity: UserIdentity, agent_version) -> None:
        del session
        if identity.tenant_id != agent_version.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent access denied.")

    async def resolve_virtual_key(self, session: AsyncSession, agent_version, context: RequestContext) -> str:
        del session, agent_version, context
        return "sk-local-master-key"
