from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import CostBudget, LlmProvider, LlmUsageRecord
from aura.domain.contracts import BudgetAction, BudgetScope, BudgetWindow, LlmTaskType, RequestContext


@dataclass(slots=True)
class UsageContext:
    provider_id: UUID
    provider_key: str
    model_name: str
    task_type: LlmTaskType
    space_id: UUID | None = None
    conversation_id: UUID | None = None
    agent_run_id: UUID | None = None
    credential_id: UUID | None = None


class CostManagementService:
    async def create_or_update_budget(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        scope_type: BudgetScope,
        scope_ref: str,
        provider_id: UUID | None,
        model_name: str | None,
        window: BudgetWindow,
        soft_limit_usd: Decimal | None,
        hard_limit_usd: Decimal,
        action_on_hard_limit: BudgetAction,
    ) -> CostBudget:
        statement = select(CostBudget).where(
            CostBudget.tenant_id == context.tenant_id,
            CostBudget.scope_type == scope_type.value,
            CostBudget.scope_ref == scope_ref,
            CostBudget.window == window.value,
        )
        statement = statement.where(CostBudget.provider_id.is_(None) if provider_id is None else CostBudget.provider_id == provider_id)
        statement = statement.where(CostBudget.model_name.is_(None) if model_name is None else CostBudget.model_name == model_name)
        budget = await session.scalar(statement)
        if budget is None:
            budget = CostBudget(
                tenant_id=context.tenant_id,
                scope_type=scope_type.value,
                scope_ref=scope_ref,
                provider_id=provider_id,
                model_name=model_name,
                window=window.value,
                soft_limit_usd=float(soft_limit_usd) if soft_limit_usd is not None else None,
                hard_limit_usd=float(hard_limit_usd),
                action_on_hard_limit=action_on_hard_limit.value,
                is_active=True,
                created_by=context.identity.user_id,
            )
            session.add(budget)
        else:
            budget.soft_limit_usd = float(soft_limit_usd) if soft_limit_usd is not None else None
            budget.hard_limit_usd = float(hard_limit_usd)
            budget.action_on_hard_limit = action_on_hard_limit.value
            budget.is_active = True
        await session.flush()
        return budget

    async def list_budgets(self, session: AsyncSession, tenant_id: UUID) -> list[CostBudget]:
        rows = await session.execute(
            select(CostBudget).where(CostBudget.tenant_id == tenant_id).order_by(CostBudget.scope_type, CostBudget.scope_ref)
        )
        return list(rows.scalars().all())

    async def check_budget(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        usage: UsageContext,
        projected_cost_usd: Decimal = Decimal("0"),
    ) -> None:
        budgets = await self._load_matching_budgets(session, context.tenant_id, usage, context.identity.user_id)
        for budget in budgets:
            spent = await self._sum_cost_for_budget(session, context, usage, budget)
            if Decimal(str(spent)) + projected_cost_usd < Decimal(str(budget.hard_limit_usd)):
                continue
            if budget.action_on_hard_limit == BudgetAction.warn_only.value:
                continue
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Budget exceeded for scope '{budget.scope_type}:{budget.scope_ref}' "
                    f"on provider '{usage.provider_key}' and model '{usage.model_name}'."
                ),
            )

    async def record_usage(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        usage: UsageContext,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: Decimal,
    ) -> LlmUsageRecord:
        record = LlmUsageRecord(
            tenant_id=context.tenant_id,
            user_id=context.identity.user_id,
            provider_id=usage.provider_id,
            credential_id=usage.credential_id,
            model_name=usage.model_name,
            task_type=usage.task_type.value,
            space_id=usage.space_id,
            conversation_id=usage.conversation_id,
            agent_run_id=usage.agent_run_id,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            estimated_cost_usd=float(estimated_cost_usd),
            measured_at=context.now_utc,
            trace_id=context.trace_id,
        )
        session.add(record)
        await session.flush()
        return record

    async def aggregate_usage(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        days: int = 30,
    ) -> list[dict[str, object]]:
        start_at = datetime.now(UTC) - timedelta(days=days)
        rows = await session.execute(
            select(
                LlmUsageRecord.provider_id,
                LlmProvider.provider_key,
                LlmUsageRecord.model_name,
                LlmUsageRecord.task_type,
                LlmUsageRecord.user_id,
                LlmUsageRecord.space_id,
                func.count(LlmUsageRecord.id),
                func.sum(LlmUsageRecord.input_tokens),
                func.sum(LlmUsageRecord.output_tokens),
                func.sum(LlmUsageRecord.estimated_cost_usd),
            )
            .join(LlmProvider, LlmProvider.id == LlmUsageRecord.provider_id)
            .where(
                LlmUsageRecord.tenant_id == tenant_id,
                LlmUsageRecord.measured_at >= start_at,
            )
            .group_by(
                LlmUsageRecord.provider_id,
                LlmProvider.provider_key,
                LlmUsageRecord.model_name,
                LlmUsageRecord.task_type,
                LlmUsageRecord.user_id,
                LlmUsageRecord.space_id,
            )
            .order_by(func.sum(LlmUsageRecord.estimated_cost_usd).desc())
        )
        aggregates: list[dict[str, object]] = []
        for provider_id, provider_key, model_name, task_type, user_id, space_id, calls, input_tokens, output_tokens, cost in rows.all():
            aggregates.append(
                {
                    "provider_id": provider_id,
                    "provider_key": provider_key,
                    "model_name": model_name,
                    "task_type": task_type,
                    "user_id": user_id,
                    "space_id": space_id,
                    "calls": int(calls or 0),
                    "input_tokens": int(input_tokens or 0),
                    "output_tokens": int(output_tokens or 0),
                    "estimated_cost_usd": float(cost or 0),
                }
            )
        return aggregates

    def estimate_cost(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        input_cost_per_1k: Decimal,
        output_cost_per_1k: Decimal,
    ) -> Decimal:
        return (
            (Decimal(input_tokens) / Decimal(1000)) * input_cost_per_1k
            + (Decimal(output_tokens) / Decimal(1000)) * output_cost_per_1k
        )

    async def _load_matching_budgets(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        usage: UsageContext,
        user_id: UUID,
    ) -> list[CostBudget]:
        scope_refs = {
            BudgetScope.tenant.value: "tenant",
            BudgetScope.user.value: str(user_id),
            BudgetScope.provider.value: str(usage.provider_id),
        }
        if usage.space_id is not None:
            scope_refs[BudgetScope.space.value] = str(usage.space_id)
        rows = await session.execute(
            select(CostBudget).where(
                CostBudget.tenant_id == tenant_id,
                CostBudget.is_active.is_(True),
                CostBudget.scope_type.in_(list(scope_refs.keys())),
            )
        )
        budgets = []
        for budget in rows.scalars().all():
            if scope_refs.get(budget.scope_type) != budget.scope_ref:
                continue
            if budget.provider_id is not None and budget.provider_id != usage.provider_id:
                continue
            if budget.model_name is not None and budget.model_name != usage.model_name:
                continue
            budgets.append(budget)
        return budgets

    async def _sum_cost_for_budget(
        self,
        session: AsyncSession,
        context: RequestContext,
        usage: UsageContext,
        budget: CostBudget,
    ) -> Decimal:
        start_at = self._window_start(context.now_utc, budget.window)
        statement = select(func.sum(LlmUsageRecord.estimated_cost_usd)).where(
            LlmUsageRecord.tenant_id == context.tenant_id,
            LlmUsageRecord.measured_at >= start_at,
        )
        if budget.scope_type == BudgetScope.user.value:
            statement = statement.where(LlmUsageRecord.user_id == context.identity.user_id)
        elif budget.scope_type == BudgetScope.provider.value:
            statement = statement.where(LlmUsageRecord.provider_id == usage.provider_id)
        elif budget.scope_type == BudgetScope.space.value:
            statement = statement.where(LlmUsageRecord.space_id == usage.space_id)
        if budget.provider_id is not None:
            statement = statement.where(LlmUsageRecord.provider_id == budget.provider_id)
        if budget.model_name is not None:
            statement = statement.where(LlmUsageRecord.model_name == budget.model_name)
        value = await session.scalar(statement)
        return Decimal(str(value or 0))

    def _window_start(self, now_utc: datetime, window: str) -> datetime:
        if window == BudgetWindow.daily.value:
            return now_utc.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return now_utc.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
