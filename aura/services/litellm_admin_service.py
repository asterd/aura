from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.domain.contracts import BudgetScope, RequestContext
from aura.services.cost_management_service import CostManagementService
from aura.services.llm_provider_service import LlmProviderService
from aura.utils.secrets import EnvSecretStore, SecretStore


@dataclass(slots=True)
class TenantRuntimeKeyState:
    key_name: str
    models: list[str]
    max_budget_usd: float | None
    rpm_limit: int | None
    synced: bool
    sync_mode: str
    error: str | None
    proxy_key: str


class LiteLLMAdminService:
    def __init__(
        self,
        *,
        llm_provider_service: LlmProviderService | None = None,
        cost_management_service: CostManagementService | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._base_url = str(settings.litellm_base_url).rstrip("/")
        self._admin_key = settings.litellm_master_key.get_secret_value()
        self._providers = llm_provider_service or LlmProviderService()
        self._costs = cost_management_service or CostManagementService()
        self._secret_store = secret_store or EnvSecretStore()

    async def ensure_tenant_runtime_key(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
    ) -> TenantRuntimeKeyState:
        key_name = self._key_name(context.tenant_id)
        models, rpm_limit = await self._load_models_and_limits(session, context.tenant_id)
        max_budget = await self._load_tenant_budget(session, context)
        fallback = TenantRuntimeKeyState(
            key_name=key_name,
            models=models,
            max_budget_usd=float(max_budget) if max_budget is not None else None,
            rpm_limit=rpm_limit,
            synced=False,
            sync_mode="master-key-fallback",
            error=None,
            proxy_key=self._admin_key,
        )
        if not settings.litellm_proxy_key_sync_enabled:
            fallback.sync_mode = "disabled"
            return fallback
        if not models:
            fallback.error = "No enabled tenant models are configured."
            return fallback

        secret_ref = self._secret_ref(context.tenant_id)
        metadata: dict[str, object] = {
            "aura_managed": True,
            "aura_key_name": key_name,
            "tenant_id": str(context.tenant_id),
            "tenant_user_id": str(context.identity.user_id),
        }
        payload: dict[str, object] = {
            "models": models,
            "duration": settings.litellm_proxy_key_duration,
            "metadata": metadata,
        }
        if max_budget is not None:
            payload["max_budget"] = float(max_budget)
        if rpm_limit is not None:
            payload["rpm_limit"] = rpm_limit

        try:
            current_key = await self._secret_store.get(secret_ref)
        except Exception:
            current_key = None

        try:
            if current_key:
                response = await self._request("POST", "/key/update", {"key": current_key, **payload})
                proxy_key = str(response.get("key") or current_key)
                await self._secret_store.put(secret_ref, proxy_key)
                return TenantRuntimeKeyState(
                    key_name=key_name,
                    models=models,
                    max_budget_usd=float(max_budget) if max_budget is not None else None,
                    rpm_limit=rpm_limit,
                    synced=True,
                    sync_mode="updated",
                    error=None,
                    proxy_key=proxy_key,
                )

            response = await self._request("POST", "/key/generate", payload)
            proxy_key = str(response["key"])
            await self._secret_store.put(secret_ref, proxy_key)
            return TenantRuntimeKeyState(
                key_name=key_name,
                models=models,
                max_budget_usd=float(max_budget) if max_budget is not None else None,
                rpm_limit=rpm_limit,
                synced=True,
                sync_mode="generated",
                error=None,
                proxy_key=proxy_key,
            )
        except Exception as exc:
            fallback.error = str(exc)
            return fallback

    async def get_tenant_runtime_key_state(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
    ) -> TenantRuntimeKeyState:
        return await self.ensure_tenant_runtime_key(session=session, context=context)

    async def _load_models_and_limits(self, session: AsyncSession, tenant_id: UUID) -> tuple[list[str], int | None]:
        rows = await self._providers.list_tenant_models(session, tenant_id)
        models: list[str] = []
        rpm_values: list[int] = []
        for model_config, _, _ in rows:
            if model_config.status != "enabled":
                continue
            runtime_name = model_config.litellm_model_name or model_config.model_name
            if runtime_name not in models:
                models.append(runtime_name)
            if model_config.rate_limit_rpm is not None:
                rpm_values.append(int(model_config.rate_limit_rpm))
        return models, (min(rpm_values) if rpm_values else None)

    async def _load_tenant_budget(self, session: AsyncSession, context: RequestContext) -> Decimal | None:
        budgets = await self._costs.list_budgets(session, context.tenant_id)
        tenant_limits: list[Decimal] = []
        for budget in budgets:
            if not budget.is_active or budget.scope_type != BudgetScope.tenant.value or budget.scope_ref != "tenant":
                continue
            if budget.provider_id is not None or budget.model_name is not None:
                continue
            tenant_limits.append(Decimal(str(budget.hard_limit_usd)))
        if not tenant_limits:
            return None
        return min(tenant_limits)

    async def _request(self, method: str, path: str, payload: dict[str, object]) -> dict[str, object]:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
            response = await client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {self._admin_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def _key_name(self, tenant_id: UUID) -> str:
        return f"aura-tenant-{tenant_id}"

    def _secret_ref(self, tenant_id: UUID) -> str:
        return f"env://AURA_LITELLM_VIRTUAL_KEY_{str(tenant_id).replace('-', '_').upper()}"
