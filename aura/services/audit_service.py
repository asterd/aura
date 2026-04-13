from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from aura.domain.contracts import RequestContext


logger = logging.getLogger("aura")


class AuditService:
    async def emit_agent_run(self, *, session: AsyncSession, context: RequestContext, run_id) -> None:
        del session
        logger.info("agent_run_emitted trace_id=%s run_id=%s tenant_id=%s", context.trace_id, run_id, context.tenant_id)
