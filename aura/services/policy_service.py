from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import ModelPolicy as ModelPolicyModel
from aura.adapters.db.models import PiiPolicy as PiiPolicyModel
from aura.adapters.db.models import SandboxPolicy as SandboxPolicyModel
from aura.domain.contracts import ModelPolicy, PiiPolicy, RequestContext, SandboxPolicy


class PolicyService:
    async def resolve_model_policy(
        self,
        session: AsyncSession,
        entity: Any,
        context: RequestContext,
    ) -> ModelPolicy:
        policy = await self._resolve_policy(
            session=session,
            model=ModelPolicyModel,
            tenant_id=context.tenant_id,
            entity=entity,
            field_name="model_policy_id",
        )
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No model policy configured for tenant.",
            )
        return ModelPolicy.model_validate(policy, from_attributes=True)

    async def resolve_pii_policy(
        self,
        session: AsyncSession,
        entity: Any,
        context: RequestContext,
    ) -> PiiPolicy | None:
        policy = await self._resolve_policy(
            session=session,
            model=PiiPolicyModel,
            tenant_id=context.tenant_id,
            entity=entity,
            field_name="pii_policy_id",
        )
        if policy is None:
            return None
        return PiiPolicy.model_validate(policy, from_attributes=True)

    async def resolve_sandbox_policy(
        self,
        session: AsyncSession,
        entity: Any,
        context: RequestContext,
    ) -> SandboxPolicy:
        policy = await self._resolve_policy(
            session=session,
            model=SandboxPolicyModel,
            tenant_id=context.tenant_id,
            entity=entity,
            field_name="sandbox_policy_id",
        )
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No sandbox policy configured for tenant.",
            )
        return SandboxPolicy.model_validate(policy, from_attributes=True)

    async def _resolve_policy(
        self,
        *,
        session: AsyncSession,
        model: type[ModelPolicyModel] | type[PiiPolicyModel] | type[SandboxPolicyModel],
        tenant_id,
        entity,
        field_name: str,
    ):
        policy_id = self._resolve_candidate_policy_id(entity, field_name)
        if policy_id is not None:
            return await session.scalar(
                select(model).where(
                    model.tenant_id == tenant_id,
                    model.id == policy_id,
                )
            )
        return await session.scalar(
            select(model).where(
                model.tenant_id == tenant_id,
                model.is_default.is_(True),
            )
        )

    def _resolve_candidate_policy_id(self, entity: Any, field_name: str):
        candidates: list[Any]
        if entity is None:
            return None
        if isinstance(entity, Iterable) and not isinstance(entity, (str, bytes, dict)):
            candidates = list(entity)
        else:
            candidates = [entity]

        if not candidates:
            return None

        first_candidate = candidates[0]
        first_policy_id = getattr(first_candidate, field_name, None)
        if first_policy_id is not None:
            return first_policy_id

        discovered_policy_ids = {
            policy_id
            for candidate in candidates[1:]
            if (policy_id := getattr(candidate, field_name, None)) is not None
        }
        if len(discovered_policy_ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Conflicting policy bindings found across the selected entities.",
            )
        return next(iter(discovered_policy_ids), None)
