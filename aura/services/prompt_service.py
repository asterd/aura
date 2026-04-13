from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import KnowledgeSpace, ToneProfile
from aura.domain.contracts import ChatRequest, RequestContext, RetrievalResult


class PromptNotResolvableError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class PromptService:
    def __init__(self) -> None:
        self._fallback_dir = Path(__file__).resolve().parents[2] / "registries" / "prompts" / "defaults"
        self._langfuse_base_url = str(settings.langfuse_base_url).rstrip("/")
        self._langfuse_secret = settings.langfuse_secret_key.get_secret_value()

    async def resolve_prompt(self, prompt_id: str) -> str:
        try:
            prompt = await self._resolve_prompt_from_langfuse(prompt_id)
        except Exception:
            prompt = None
        if prompt:
            return prompt

        fallback_path = self._fallback_dir / f"{prompt_id}.txt"
        if fallback_path.exists():
            logger.warning("langfuse_unavailable_using_fallback", extra={"prompt_id": prompt_id})
            return fallback_path.read_text(encoding="utf-8").strip()
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

    async def _resolve_prompt_from_langfuse(self, prompt_id: str) -> str | None:
        headers = {"Authorization": f"Bearer {self._langfuse_secret}"}
        async with httpx.AsyncClient(base_url=self._langfuse_base_url, timeout=5.0) as client:
            response = await client.get(f"/api/public/prompts/{prompt_id}", headers=headers)
            response.raise_for_status()
        payload = response.json()
        prompt = payload.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return prompt.strip()
        if isinstance(payload.get("text"), str) and payload["text"].strip():
            return payload["text"].strip()
        return None
