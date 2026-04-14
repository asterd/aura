from __future__ import annotations

from collections.abc import AsyncGenerator
import logging

from fastapi import HTTPException, status
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import KnowledgeSpace
from aura.domain.contracts import (
    AgentRunResult,
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
    ChatStreamEventCitation,
    ChatStreamEventDone,
    ChatStreamEventError,
    ChatStreamEventToken,
    RequestContext,
    RetrievalRequest,
    RetrievalResult,
)
from aura.services.conversation_service import ConversationService
from aura.services.llm_service import LlmService, LiteLLMUnavailableError
from aura.services.pii_service import PiiService
from aura.services.policy_service import PolicyService
from aura.services.prompt_service import PromptService
from aura.services.retrieval import RetrievalService


logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        *,
        retrieval_service: RetrievalService | None = None,
        prompt_service: PromptService | None = None,
        pii_service: PiiService | None = None,
        llm_service: LlmService | None = None,
        conversation_service: ConversationService | None = None,
        policy_service: PolicyService | None = None,
    ) -> None:
        self._retrieval = retrieval_service or RetrievalService()
        self._prompt = prompt_service or PromptService()
        self._pii = pii_service or PiiService()
        self._llm = llm_service or LlmService()
        self._conversations = conversation_service or ConversationService()
        self._policies = policy_service or PolicyService()

    def _empty_retrieval_result(self, request: ChatRequest) -> RetrievalResult:
        """Return an empty RetrievalResult for free-chat mode (no space_ids)."""
        return RetrievalResult(query=request.message)

    async def respond(
        self,
        *,
        session: AsyncSession,
        request: ChatRequest,
        context: RequestContext,
    ) -> ChatResponse:
        if request.space_ids:
            retrieval_result = await self._retrieval.retrieve(
                session=session,
                request=RetrievalRequest(
                    query=request.message,
                    space_ids=request.space_ids,
                    conversation_id=request.conversation_id,
                    retrieval_profile_id=request.retrieval_profile_id,
                ),
                context=context,
            )
        else:
            retrieval_result = self._empty_retrieval_result(request)
        return await self.respond_with_context(
            session=session,
            request=request,
            retrieval_result=retrieval_result,
            context=context,
        )

    async def respond_stream(
        self,
        *,
        session: AsyncSession,
        request: ChatRequest,
        context: RequestContext,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        if request.space_ids:
            retrieval_result = await self._retrieval.retrieve(
                session=session,
                request=RetrievalRequest(
                    query=request.message,
                    space_ids=request.space_ids,
                    conversation_id=request.conversation_id,
                    retrieval_profile_id=request.retrieval_profile_id,
                ),
                context=context,
            )
        else:
            retrieval_result = self._empty_retrieval_result(request)
        async for event in self.respond_stream_with_context(
            session=session,
            request=request,
            retrieval_result=retrieval_result,
            context=context,
        ):
            yield event

    async def respond_with_context(
        self,
        *,
        session: AsyncSession,
        request: ChatRequest,
        retrieval_result,
        context: RequestContext,
        agent_runs: list[dict[str, str | AgentRunResult]] | None = None,
    ) -> ChatResponse:
        spaces = await self._load_spaces(session, request.space_ids)
        prompt = await self._prompt.build_prompt_stack(
            session=session,
            context=context,
            request=request,
            retrieval_result=retrieval_result,
        )
        model_policy = await self._policies.resolve_model_policy(session, spaces, context)
        model_name = self._resolve_model_name(request=request, model_policy=model_policy)
        input_transform = await self._pii.transform_input_if_needed(
            session=session,
            context=context,
            text=request.message,
            policy_entity=spaces,
        )
        user_persisted_transform = await self._pii.transform_persisted_text_if_needed(
            session=session,
            context=context,
            text=request.message,
            policy_entity=spaces,
        )
        log_transform = await self._pii.transform_log_text_if_needed(
            session=session,
            context=context,
            text=request.message,
            policy_entity=spaces,
        )
        logger.log(
            logging.WARNING if log_transform.had_transformations else logging.INFO,
            "chat_request_received trace_id=%s tenant_id=%s content=%s",
            context.trace_id,
            context.tenant_id,
            log_transform.transformed_text,
        )
        try:
            llm_result = await self._llm.generate(
                session=session,
                prompt=prompt,
                transformed_user_text=input_transform.transformed_text,
                model_override=model_name,
                context=context,
                space_ids=request.space_ids,
                conversation_id=request.conversation_id,
            )
        except LiteLLMUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LiteLLM unavailable.",
            ) from exc
        output_transform = await self._pii.transform_output_if_needed(
            session=session,
            context=context,
            text=llm_result.content,
            policy_entity=spaces,
        )
        assistant_persisted_transform = await self._pii.transform_persisted_text_if_needed(
            session=session,
            context=context,
            text=llm_result.content,
            policy_entity=spaces,
        )
        persisted = await self._conversations.persist_assistant_message(
            session=session,
            context=context,
            request=request,
            retrieval_result=retrieval_result,
            persisted_user_text=user_persisted_transform.transformed_text,
            final_text=assistant_persisted_transform.transformed_text,
            model_used=llm_result.model_used,
            tokens_used=llm_result.tokens_used,
            agent_runs=agent_runs,
        )
        return ChatResponse(
            conversation_id=persisted.conversation_id,
            message_id=persisted.message_id,
            content=output_transform.transformed_text,
            citations=retrieval_result.citations,
            trace_id=context.trace_id,
        )

    async def respond_stream_with_context(
        self,
        *,
        session: AsyncSession,
        request: ChatRequest,
        retrieval_result,
        context: RequestContext,
        agent_runs: list[dict[str, str | AgentRunResult]] | None = None,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        try:
            spaces = await self._load_spaces(session, request.space_ids)
            prompt = await self._prompt.build_prompt_stack(
                session=session,
                context=context,
                request=request,
                retrieval_result=retrieval_result,
            )
            model_policy = await self._policies.resolve_model_policy(session, spaces, context)
            model_name = self._resolve_model_name(request=request, model_policy=model_policy)
            input_transform = await self._pii.transform_input_if_needed(
                session=session,
                context=context,
                text=request.message,
                policy_entity=spaces,
            )
            user_persisted_transform = await self._pii.transform_persisted_text_if_needed(
                session=session,
                context=context,
                text=request.message,
                policy_entity=spaces,
            )
            log_transform = await self._pii.transform_log_text_if_needed(
                session=session,
                context=context,
                text=request.message,
                policy_entity=spaces,
            )
            logger.log(
                logging.WARNING if log_transform.had_transformations else logging.INFO,
                "chat_stream_received trace_id=%s tenant_id=%s content=%s",
                context.trace_id,
                context.tenant_id,
                log_transform.transformed_text,
            )
            raw_chunks: list[str] = []
            emitted_chunks: list[str] = []
            boundary_buffer = ""

            try:
                async for token in self._llm.stream_generate(
                    session=session,
                    prompt=prompt,
                    transformed_user_text=input_transform.transformed_text,
                    model_override=model_name,
                    context=context,
                    space_ids=request.space_ids,
                    conversation_id=request.conversation_id,
                ):
                    raw_chunks.append(token)
                    boundary_buffer += token
                    flushable, boundary_buffer = self._split_boundary_buffer(boundary_buffer)
                    if not flushable:
                        continue
                    cleaned = await self._pii.transform_output_if_needed(
                        session=session,
                        context=context,
                        text=flushable,
                        policy_entity=spaces,
                    )
                    emitted_chunks.append(cleaned.transformed_text)
                    yield ChatStreamEventToken(type="token", content=cleaned.transformed_text)
            except LiteLLMUnavailableError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="LiteLLM unavailable.",
                ) from exc

            if boundary_buffer:
                cleaned_tail = await self._pii.transform_output_if_needed(
                    session=session,
                    context=context,
                    text=boundary_buffer,
                    policy_entity=spaces,
                )
                emitted_chunks.append(cleaned_tail.transformed_text)
                yield ChatStreamEventToken(type="token", content=cleaned_tail.transformed_text)

            for citation in retrieval_result.citations:
                yield ChatStreamEventCitation(type="citation", citation=citation)

            assistant_persisted_transform = await self._pii.transform_persisted_text_if_needed(
                session=session,
                context=context,
                text="".join(raw_chunks).strip(),
                policy_entity=spaces,
            )
            persisted = await self._conversations.persist_assistant_message(
                session=session,
                context=context,
                request=request,
                retrieval_result=retrieval_result,
                persisted_user_text=user_persisted_transform.transformed_text,
                final_text=assistant_persisted_transform.transformed_text,
                model_used=None,
                tokens_used=None,
                agent_runs=agent_runs,
            )
            yield ChatStreamEventDone(type="done", message_id=persisted.message_id, trace_id=context.trace_id)
        except Exception as exc:
            yield ChatStreamEventError(type="error", code="chat_stream_failed", message=str(exc))

    async def _load_spaces(self, session: AsyncSession, space_ids: list) -> list[KnowledgeSpace]:
        spaces = (
            await session.execute(select(KnowledgeSpace).where(KnowledgeSpace.id.in_(space_ids)))
        ).scalars().all()
        by_id = {space.id: space for space in spaces}
        return [by_id[space_id] for space_id in space_ids if space_id in by_id]

    def _resolve_model_name(self, *, request: ChatRequest, model_policy) -> str:
        if request.model_override is None:
            return model_policy.default_model

        allowed_models = set(model_policy.allowed_models) if model_policy.allowed_models else {model_policy.default_model}
        if request.model_override not in allowed_models:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Model override '{request.model_override}' is not allowed by policy.",
            )
        return request.model_override

    def _split_boundary_buffer(self, text: str) -> tuple[str, str]:
        last_boundary = max(text.rfind("."), text.rfind("!"), text.rfind("?"), text.rfind("\n"))
        if last_boundary == -1:
            return "", text
        split_at = last_boundary + 1
        return text[:split_at], text[split_at:]
