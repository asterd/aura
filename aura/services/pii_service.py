from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from aura.domain.contracts import PiiTransformResult, RequestContext


class PiiService:
    async def transform_input_if_needed(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        text: str,
    ) -> PiiTransformResult:
        return PiiTransformResult(
            mode="noop",
            transformed_text=text,
            detected_entities=[],
            mapping_refs=[],
            had_transformations=False,
        )

    async def transform_output_if_needed(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        text: str,
    ) -> PiiTransformResult:
        return PiiTransformResult(
            mode="noop",
            transformed_text=text,
            detected_entities=[],
            mapping_refs=[],
            had_transformations=False,
        )
