from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.langfuse.client import LangfuseClient, LangfuseUnavailableError
from aura.adapters.db.models import KnowledgeSpace, ToneProfile
from aura.domain.contracts import ChatRequest, RetrievalResult
from aura.utils.observability import get_current_trace_id


class PromptNotResolvableError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class PromptService:
    def __init__(self, *, langfuse_client: LangfuseClient | None = None) -> None:
        self._fallback_dir = Path(__file__).resolve().parents[2] / "registries" / "prompts" / "defaults"
        self._langfuse = langfuse_client or LangfuseClient()

    async def resolve_prompt(self, prompt_id: str) -> str:
        try:
            return await self._langfuse.get_prompt(prompt_id)
        except LangfuseUnavailableError:
            fallback_prompt = self._langfuse.load_fallback_prompt(prompt_id)
            if fallback_prompt:
                logger.warning(
                    "langfuse_unavailable_using_fallback trace_id=%s prompt_id=%s",
                    get_current_trace_id(),
                    prompt_id,
                )
                return fallback_prompt
        raise PromptNotResolvableError(prompt_id)

    async def resolve_optional_prompt(self, prompt_id: str) -> str:
        try:
            return await self.resolve_prompt(prompt_id)
        except PromptNotResolvableError:
            return ""

    async def build_prompt_stack(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        request: ChatRequest,
        retrieval_result: RetrievalResult,
    ) -> list[dict[str, str]]:
        spaces = (
            await session.execute(select(KnowledgeSpace).where(KnowledgeSpace.id.in_(request.space_ids)))
        ).scalars().all()
        spaces_by_id = {space.id: space for space in spaces}
        ordered_spaces = [spaces_by_id[space_id] for space_id in request.space_ids if space_id in spaces_by_id]
        tone_prompt = await self._resolve_tenant_tone_prompt(session, context.tenant_id, ordered_spaces)
        space_instructions = "\n\n".join(
            space.system_instructions.strip()
            for space in ordered_spaces
            if space.system_instructions and space.system_instructions.strip()
        )
        context_block = "\n\n".join(retrieval_result.context_blocks).strip()

        stack: list[dict[str, str]] = [
            {"role": "system", "content": await self.resolve_prompt("platform_system_prompt")},
            {"role": "system", "content": tone_prompt},
            {"role": "system", "content": await self.resolve_optional_prompt("guardrail_policy_prompt")},
            {"role": "system", "content": space_instructions},
            {"role": "system", "content": await self._resolve_agent_prompt(request)},
            {"role": "system", "content": request.additional_instructions or ""},
            {"role": "system", "content": context_block},
            {"role": "user", "content": request.message},
        ]
        return stack

    async def _resolve_tenant_tone_prompt(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        spaces: list[KnowledgeSpace],
    ) -> str:
        tone_profile_id = next((space.tone_profile_id for space in spaces if space.tone_profile_id is not None), None)
        statement = select(ToneProfile.prompt_snippet).where(ToneProfile.tenant_id == tenant_id)
        if tone_profile_id is not None:
            statement = statement.where(ToneProfile.id == tone_profile_id)
        else:
            statement = statement.where(ToneProfile.name == "default")
        prompt = (await session.execute(statement)).scalar_one_or_none()
        return prompt or ""

    async def _resolve_agent_prompt(self, request: ChatRequest) -> str:
        if not request.active_agent_ids:
            return ""
        return await self.resolve_optional_prompt("agent_prompt")

    async def resolve_agent_prompt(self) -> str:
        return await self.resolve_optional_prompt("agent_prompt")
