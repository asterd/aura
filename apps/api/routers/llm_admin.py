from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import cost_management_service, litellm_admin_service, llm_provider_service
from aura.domain.contracts import BudgetAction, BudgetScope, BudgetWindow, LlmTaskType, RequestContext


router = APIRouter(prefix="/api/v1/admin/llm", tags=["llm-admin"])


class ProviderResponse(BaseModel):
    id: UUID
    provider_key: str
    display_name: str
    description: str | None = None
    supports_chat: bool
    supports_embeddings: bool
    supports_reasoning: bool
    supports_tools: bool
    base_url_hint: str | None = None
    status: str


class CreateCredentialRequest(BaseModel):
    provider_key: str
    name: str
    secret_ref: str | None = None
    api_key: SecretStr | None = None
    endpoint_override: str | None = None
    is_default: bool = False


class CredentialResponse(BaseModel):
    id: UUID
    provider_id: UUID
    provider_key: str
    name: str
    secret_ref: str
    endpoint_override: str | None = None
    is_default: bool
    status: str


class EnableModelRequest(BaseModel):
    credential_id: UUID
    task_type: LlmTaskType
    model_name: str
    alias: str | None = None
    litellm_model_name: str | None = None
    input_cost_per_1k: Decimal | None = None
    output_cost_per_1k: Decimal | None = None
    rate_limit_rpm: int | None = None
    concurrency_limit: int | None = None
    is_default: bool = False


class ModelConfigResponse(BaseModel):
    id: UUID
    provider_id: UUID
    provider_key: str
    credential_id: UUID
    credential_name: str
    task_type: str
    model_name: str
    alias: str | None = None
    litellm_model_name: str | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    rate_limit_rpm: int | None = None
    concurrency_limit: int | None = None
    is_default: bool
    status: str


class CreateBudgetRequest(BaseModel):
    scope_type: BudgetScope
    scope_ref: str
    provider_id: UUID | None = None
    model_name: str | None = None
    window: BudgetWindow
    soft_limit_usd: Decimal | None = None
    hard_limit_usd: Decimal = Field(gt=0)
    action_on_hard_limit: BudgetAction = BudgetAction.block


class BudgetResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_ref: str
    provider_id: UUID | None = None
    model_name: str | None = None
    window: str
    soft_limit_usd: float | None = None
    hard_limit_usd: float
    action_on_hard_limit: str
    is_active: bool


class RuntimeKeyResponse(BaseModel):
    key_name: str
    models: list[str]
    max_budget_usd: float | None = None
    rpm_limit: int | None = None
    synced: bool
    sync_mode: str
    error: str | None = None


def _require_admin(context: RequestContext) -> None:
    if set(context.identity.roles).intersection({"admin", "tenant_admin", "platform_admin"}):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role required.")


def _to_provider_response(provider) -> ProviderResponse:
    return ProviderResponse.model_validate(provider, from_attributes=True)


def _to_credential_response(credential, provider) -> CredentialResponse:
    return CredentialResponse(
        id=credential.id,
        provider_id=provider.id,
        provider_key=provider.provider_key,
        name=credential.name,
        secret_ref=credential.secret_ref,
        endpoint_override=credential.endpoint_override,
        is_default=credential.is_default,
        status=credential.status,
    )


def _to_model_config_response(model_config, credential, provider) -> ModelConfigResponse:
    return ModelConfigResponse(
        id=model_config.id,
        provider_id=provider.id,
        provider_key=provider.provider_key,
        credential_id=credential.id,
        credential_name=credential.name,
        task_type=model_config.task_type,
        model_name=model_config.model_name,
        alias=model_config.alias,
        litellm_model_name=model_config.litellm_model_name,
        input_cost_per_1k=float(model_config.input_cost_per_1k) if model_config.input_cost_per_1k is not None else None,
        output_cost_per_1k=float(model_config.output_cost_per_1k) if model_config.output_cost_per_1k is not None else None,
        rate_limit_rpm=model_config.rate_limit_rpm,
        concurrency_limit=model_config.concurrency_limit,
        is_default=model_config.is_default,
        status=model_config.status,
    )


def _to_budget_response(budget) -> BudgetResponse:
    return BudgetResponse(
        id=budget.id,
        scope_type=budget.scope_type,
        scope_ref=budget.scope_ref,
        provider_id=budget.provider_id,
        model_name=budget.model_name,
        window=budget.window,
        soft_limit_usd=float(budget.soft_limit_usd) if budget.soft_limit_usd is not None else None,
        hard_limit_usd=float(budget.hard_limit_usd),
        action_on_hard_limit=budget.action_on_hard_limit,
        is_active=budget.is_active,
    )


@router.get("/providers", response_model=list[ProviderResponse])
async def list_supported_providers(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderResponse]:
    _require_admin(context)
    providers = await llm_provider_service.list_supported_providers(session)
    return [_to_provider_response(provider) for provider in providers]


@router.post("/credentials", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def register_credential(
    request: CreateCredentialRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> CredentialResponse:
    _require_admin(context)
    credential = await llm_provider_service.register_credential(
        session=session,
        context=context,
        provider_key=request.provider_key,
        name=request.name,
        secret_ref=request.secret_ref,
        api_key=request.api_key.get_secret_value() if request.api_key else None,
        endpoint_override=request.endpoint_override,
        is_default=request.is_default,
    )
    provider = next(
        provider for provider in await llm_provider_service.list_supported_providers(session) if provider.id == credential.provider_id
    )
    await litellm_admin_service.ensure_tenant_runtime_key(session=session, context=context)
    return _to_credential_response(credential, provider)


@router.get("/credentials", response_model=list[CredentialResponse])
async def list_credentials(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[CredentialResponse]:
    _require_admin(context)
    rows = await llm_provider_service.list_tenant_credentials(session, context.tenant_id)
    return [_to_credential_response(credential, provider) for credential, provider in rows]


@router.post("/models", response_model=ModelConfigResponse, status_code=status.HTTP_201_CREATED)
async def enable_model(
    request: EnableModelRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> ModelConfigResponse:
    _require_admin(context)
    config = await llm_provider_service.enable_model(
        session=session,
        context=context,
        credential_id=request.credential_id,
        task_type=request.task_type,
        model_name=request.model_name,
        alias=request.alias,
        litellm_model_name=request.litellm_model_name,
        input_cost_per_1k=request.input_cost_per_1k,
        output_cost_per_1k=request.output_cost_per_1k,
        rate_limit_rpm=request.rate_limit_rpm,
        concurrency_limit=request.concurrency_limit,
        is_default=request.is_default,
    )
    rows = await llm_provider_service.list_tenant_models(session, context.tenant_id)
    match = next((row for row in rows if row[0].id == config.id), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Model config not found after creation.")
    model_config, credential, provider = match
    await litellm_admin_service.ensure_tenant_runtime_key(session=session, context=context)
    return _to_model_config_response(model_config, credential, provider)


@router.get("/models", response_model=list[ModelConfigResponse])
async def list_models(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelConfigResponse]:
    _require_admin(context)
    rows = await llm_provider_service.list_tenant_models(session, context.tenant_id)
    return [_to_model_config_response(model_config, credential, provider) for model_config, credential, provider in rows]


@router.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_budget(
    request: CreateBudgetRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> BudgetResponse:
    _require_admin(context)
    budget = await cost_management_service.create_or_update_budget(
        session=session,
        context=context,
        scope_type=request.scope_type,
        scope_ref=request.scope_ref,
        provider_id=request.provider_id,
        model_name=request.model_name,
        window=request.window,
        soft_limit_usd=request.soft_limit_usd,
        hard_limit_usd=request.hard_limit_usd,
        action_on_hard_limit=request.action_on_hard_limit,
    )
    await litellm_admin_service.ensure_tenant_runtime_key(session=session, context=context)
    return _to_budget_response(budget)


@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[BudgetResponse]:
    _require_admin(context)
    budgets = await cost_management_service.list_budgets(session, context.tenant_id)
    return [_to_budget_response(budget) for budget in budgets]


@router.get("/usage")
async def get_usage(
    days: int = Query(default=30, ge=1, le=365),
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    _require_admin(context)
    return {"items": await cost_management_service.aggregate_usage(session=session, tenant_id=context.tenant_id, days=days)}


@router.get("/runtime-key", response_model=RuntimeKeyResponse)
async def get_runtime_key_state(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> RuntimeKeyResponse:
    _require_admin(context)
    state = await litellm_admin_service.get_tenant_runtime_key_state(session=session, context=context)
    return RuntimeKeyResponse(
        key_name=state.key_name,
        models=state.models,
        max_budget_usd=state.max_budget_usd,
        rpm_limit=state.rpm_limit,
        synced=state.synced,
        sync_mode=state.sync_mode,
        error=state.error,
    )


@router.post("/runtime-key/sync", response_model=RuntimeKeyResponse)
async def sync_runtime_key(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> RuntimeKeyResponse:
    _require_admin(context)
    state = await litellm_admin_service.ensure_tenant_runtime_key(session=session, context=context)
    return RuntimeKeyResponse(
        key_name=state.key_name,
        models=state.models,
        max_budget_usd=state.max_budget_usd,
        rpm_limit=state.rpm_limit,
        synced=state.synced,
        sync_mode=state.sync_mode,
        error=state.error,
    )
