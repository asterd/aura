from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.domain.contracts import LlmTaskType, RequestContext, UserIdentity
from aura.services.litellm_admin_service import LiteLLMAdminService
from aura.services.llm_provider_service import LlmProviderService


class AuthzService:
    def __init__(
        self,
        *,
        llm_provider_service: LlmProviderService | None = None,
        litellm_admin_service: LiteLLMAdminService | None = None,
    ) -> None:
        self._providers = llm_provider_service or LlmProviderService()
        self._litellm_admin = litellm_admin_service or LiteLLMAdminService(llm_provider_service=self._providers)

    async def ensure_can_run_agent(self, *, session: AsyncSession, identity: UserIdentity, agent_version) -> None:
        del session
        if identity.tenant_id != agent_version.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent access denied.")

    async def resolve_virtual_key(self, session: AsyncSession, agent_version, context: RequestContext) -> str:
        default_model = (
            (agent_version.manifest.get("model_policy") or {}).get("default_model")
            if isinstance(agent_version.manifest.get("model_policy"), dict)
            else None
        )
        await self._providers.resolve_model(
            session=session,
            tenant_id=context.tenant_id,
            requested_model=default_model,
            task_type=LlmTaskType.chat,
        )
        state = await self._litellm_admin.ensure_tenant_runtime_key(session=session, context=context)
        return state.proxy_key or settings.litellm_master_key.get_secret_value()
