from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import LlmProvider, TenantModelConfig, TenantProviderCredential
from aura.domain.contracts import LlmTaskType, RequestContext
from aura.utils.secrets import EnvSecretStore, SecretStore


@dataclass(slots=True)
class ResolvedLlmRuntimeConfig:
    provider_id: UUID
    provider_key: str
    credential_id: UUID | None
    model_config_id: UUID | None
    requested_model: str
    runtime_model_name: str
    task_type: str
    provider_api_key: str
    provider_base_url: str | None
    input_cost_per_1k: Decimal
    output_cost_per_1k: Decimal


class LlmProviderService:
    def __init__(self, *, secret_store: SecretStore | None = None) -> None:
        self._secret_store = secret_store or EnvSecretStore()

    async def list_supported_providers(self, session: AsyncSession) -> list[LlmProvider]:
        rows = await session.execute(select(LlmProvider).order_by(LlmProvider.display_name))
        return list(rows.scalars().all())

    async def list_tenant_credentials(self, session: AsyncSession, tenant_id: UUID) -> list[tuple[TenantProviderCredential, LlmProvider]]:
        rows = await session.execute(
            select(TenantProviderCredential, LlmProvider)
            .join(LlmProvider, LlmProvider.id == TenantProviderCredential.provider_id)
            .where(TenantProviderCredential.tenant_id == tenant_id)
            .order_by(LlmProvider.display_name, TenantProviderCredential.name)
        )
        return [cast(tuple[TenantProviderCredential, LlmProvider], row) for row in rows.all()]

    async def register_credential(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        provider_key: str,
        name: str,
        secret_ref: str | None,
        api_key: str | None,
        endpoint_override: str | None,
        is_default: bool,
    ) -> TenantProviderCredential:
        provider = await self._require_provider(session, provider_key)
        persisted_secret_ref = secret_ref
        if api_key:
            persisted_secret_ref = self._build_secret_ref(context.tenant_id, provider.provider_key, name)
            await self._secret_store.put(persisted_secret_ref, api_key)
        if not persisted_secret_ref:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either secret_ref or api_key is required.",
            )

        if is_default:
            await self._unset_default_credentials(session, context.tenant_id, provider.id)

        credential = await session.scalar(
            select(TenantProviderCredential).where(
                TenantProviderCredential.tenant_id == context.tenant_id,
                TenantProviderCredential.provider_id == provider.id,
                TenantProviderCredential.name == name,
            )
        )
        if credential is None:
            credential = TenantProviderCredential(
                tenant_id=context.tenant_id,
                provider_id=provider.id,
                name=name,
                secret_ref=persisted_secret_ref,
                endpoint_override=endpoint_override,
                is_default=is_default,
                status="active",
                created_by=context.identity.user_id,
            )
            session.add(credential)
        else:
            credential.secret_ref = persisted_secret_ref
            credential.endpoint_override = endpoint_override
            credential.is_default = is_default
            credential.status = "active"
        await session.flush()
        return credential

    async def list_tenant_models(self, session: AsyncSession, tenant_id: UUID) -> list[tuple[TenantModelConfig, TenantProviderCredential, LlmProvider]]:
        rows = await session.execute(
            select(TenantModelConfig, TenantProviderCredential, LlmProvider)
            .join(TenantProviderCredential, TenantProviderCredential.id == TenantModelConfig.credential_id)
            .join(LlmProvider, LlmProvider.id == TenantModelConfig.provider_id)
            .where(TenantModelConfig.tenant_id == tenant_id)
            .order_by(TenantModelConfig.task_type, LlmProvider.display_name, TenantModelConfig.model_name)
        )
        return [cast(tuple[TenantModelConfig, TenantProviderCredential, LlmProvider], row) for row in rows.all()]

    async def enable_model(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        credential_id: UUID,
        task_type: LlmTaskType,
        model_name: str,
        alias: str | None,
        litellm_model_name: str | None,
        input_cost_per_1k: Decimal | None,
        output_cost_per_1k: Decimal | None,
        rate_limit_rpm: int | None,
        concurrency_limit: int | None,
        is_default: bool,
    ) -> TenantModelConfig:
        credential = await session.scalar(
            select(TenantProviderCredential).where(
                TenantProviderCredential.id == credential_id,
                TenantProviderCredential.tenant_id == context.tenant_id,
            )
        )
        if credential is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found.")

        if is_default:
            await session.execute(
                update(TenantModelConfig)
                .where(
                    TenantModelConfig.tenant_id == context.tenant_id,
                    TenantModelConfig.task_type == task_type.value,
                )
                .values(is_default=False)
            )

        config = await session.scalar(
            select(TenantModelConfig).where(
                TenantModelConfig.tenant_id == context.tenant_id,
                TenantModelConfig.provider_id == credential.provider_id,
                TenantModelConfig.credential_id == credential.id,
                TenantModelConfig.task_type == task_type.value,
                TenantModelConfig.model_name == model_name,
            )
        )
        if config is None:
            config = TenantModelConfig(
                tenant_id=context.tenant_id,
                provider_id=credential.provider_id,
                credential_id=credential.id,
                alias=alias,
                model_name=model_name,
                litellm_model_name=litellm_model_name,
                task_type=task_type.value,
                rate_limit_rpm=rate_limit_rpm,
                concurrency_limit=concurrency_limit,
                input_cost_per_1k=float(input_cost_per_1k) if input_cost_per_1k is not None else None,
                output_cost_per_1k=float(output_cost_per_1k) if output_cost_per_1k is not None else None,
                is_default=is_default,
                status="enabled",
                created_by=context.identity.user_id,
            )
            session.add(config)
        else:
            config.alias = alias
            config.litellm_model_name = litellm_model_name
            config.rate_limit_rpm = rate_limit_rpm
            config.concurrency_limit = concurrency_limit
            config.input_cost_per_1k = float(input_cost_per_1k) if input_cost_per_1k is not None else None
            config.output_cost_per_1k = float(output_cost_per_1k) if output_cost_per_1k is not None else None
            config.is_default = is_default
            config.status = "enabled"
        await session.flush()
        return config

    async def resolve_model(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        requested_model: str | None,
        task_type: LlmTaskType,
    ) -> ResolvedLlmRuntimeConfig:
        rows = await session.execute(
            select(TenantModelConfig, TenantProviderCredential, LlmProvider)
            .join(TenantProviderCredential, TenantProviderCredential.id == TenantModelConfig.credential_id)
            .join(LlmProvider, LlmProvider.id == TenantModelConfig.provider_id)
            .where(
                TenantModelConfig.tenant_id == tenant_id,
                TenantModelConfig.task_type == task_type.value,
                TenantModelConfig.status == "enabled",
                TenantProviderCredential.status == "active",
                LlmProvider.status == "active",
            )
            .order_by(TenantModelConfig.is_default.desc(), TenantModelConfig.created_at.asc())
        )
        candidates = [cast(tuple[TenantModelConfig, TenantProviderCredential, LlmProvider], row) for row in rows.all()]
        if not candidates:
            return await self._resolve_legacy_fallback(session, requested_model=requested_model, task_type=task_type)

        selected: tuple[TenantModelConfig, TenantProviderCredential, LlmProvider] | None = None
        if requested_model is not None:
            for model_config, credential, provider in candidates:
                if requested_model in {
                    model_config.alias,
                    model_config.model_name,
                    model_config.litellm_model_name,
                }:
                    selected = (model_config, credential, provider)
                    break
            if selected is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Model '{requested_model}' is not enabled for tenant.",
                )
        else:
            selected = candidates[0]

        model_config, credential, provider = selected
        provider_secret = await self._secret_store.get(credential.secret_ref)
        return ResolvedLlmRuntimeConfig(
            provider_id=provider.id,
            provider_key=provider.provider_key,
            credential_id=credential.id,
            model_config_id=model_config.id,
            requested_model=requested_model or model_config.alias or model_config.model_name,
            runtime_model_name=model_config.litellm_model_name or model_config.model_name,
            task_type=model_config.task_type,
            provider_api_key=provider_secret,
            provider_base_url=credential.endpoint_override or provider.base_url_hint,
            input_cost_per_1k=Decimal(str(model_config.input_cost_per_1k or 0)),
            output_cost_per_1k=Decimal(str(model_config.output_cost_per_1k or 0)),
        )

    async def _require_provider(self, session: AsyncSession, provider_key: str) -> LlmProvider:
        provider = await session.scalar(select(LlmProvider).where(LlmProvider.provider_key == provider_key))
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not supported.")
        if provider.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider is not active.")
        return provider

    async def _unset_default_credentials(self, session: AsyncSession, tenant_id: UUID, provider_id: UUID) -> None:
        await session.execute(
            update(TenantProviderCredential)
            .where(
                TenantProviderCredential.tenant_id == tenant_id,
                TenantProviderCredential.provider_id == provider_id,
            )
            .values(is_default=False)
        )

    def _build_secret_ref(self, tenant_id: UUID, provider_key: str, name: str) -> str:
        slug = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "DEFAULT"
        return f"env://AURA_LLM_{str(tenant_id).replace('-', '_').upper()}_{provider_key.upper()}_{slug}_{uuid4().hex[:8]}"

    async def _resolve_legacy_fallback(
        self,
        session: AsyncSession,
        *,
        requested_model: str | None,
        task_type: LlmTaskType,
    ) -> ResolvedLlmRuntimeConfig:
        provider = await session.scalar(
            select(LlmProvider)
            .where(LlmProvider.provider_key == "openai", LlmProvider.status == "active")
            .limit(1)
        )
        if provider is None:
            provider = await session.scalar(select(LlmProvider).where(LlmProvider.status == "active").limit(1))
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No active LLM provider is available.",
            )

        if task_type == LlmTaskType.embedding:
            runtime_model_name = requested_model or "text-embedding-3-small"
        else:
            runtime_model_name = requested_model or "gpt-4o-mini"
            if runtime_model_name == "gpt-4o":
                runtime_model_name = "gpt-4o-mini"
        return ResolvedLlmRuntimeConfig(
            provider_id=provider.id,
            provider_key=provider.provider_key,
            credential_id=None,
            model_config_id=None,
            requested_model=runtime_model_name,
            runtime_model_name=runtime_model_name,
            task_type=task_type.value,
            provider_api_key="",
            provider_base_url=None,
            input_cost_per_1k=Decimal("0"),
            output_cost_per_1k=Decimal("0"),
        )
