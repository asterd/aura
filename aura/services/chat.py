from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from aura.domain.contracts import (
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
    ChatStreamEventCitation,
    ChatStreamEventDone,
    ChatStreamEventError,
    ChatStreamEventToken,
    RequestContext,
    RetrievalRequest,
)
from aura.services.conversation_service import ConversationService
from aura.services.llm_service import LlmService
from aura.services.pii_service import PiiService
from aura.services.prompt_service import PromptService
from aura.services.retrieval import RetrievalService


class ChatService:
    def __init__(
        self,
        *,
        retrieval_service: RetrievalService | None = None,
        prompt_service: PromptService | None = None,
        pii_service: PiiService | None = None,
        llm_service: LlmService | None = None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self._retrieval = retrieval_service or RetrievalService()
        self._prompt = prompt_service or PromptService()
        self._pii = pii_service or PiiService()
        self._llm = llm_service or LlmService()
        self._conversations = conversation_service or ConversationService()

    async def respond(
        self,
        *,
        session: AsyncSession,
        request: ChatRequest,
        context: RequestContext,
    ) -> ChatResponse:
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
        prompt = await self._prompt.build_prompt_stack(
            session=session,
            context=context,
            request=request,
            retrieval_result=retrieval_result,
        )
        input_transform = await self._pii.transform_input_if_needed(session=session, context=context, text=request.message)
        llm_result = await self._llm.generate(
            prompt=prompt,
            transformed_user_text=input_transform.transformed_text,
            model_override=request.model_override,
            context=context,
        )
        output_transform = await self._pii.transform_output_if_needed(
            session=session,
            context=context,
            text=llm_result.content,
        )
        persisted = await self._conversations.persist_assistant_message(
            session=session,
            context=context,
            request=request,
            retrieval_result=retrieval_result,
            final_text=output_transform.transformed_text,
            model_used=llm_result.model_used,
            tokens_used=llm_result.tokens_used,
        )
        return ChatResponse(
            conversation_id=persisted.conversation_id,
            message_id=persisted.message_id,
            content=output_transform.transformed_text,
            citations=retrieval_result.citations,
            trace_id=context.trace_id,
        )

    async def respond_stream(
        self,
        *,
        session: AsyncSession,
        request: ChatRequest,
        context: RequestContext,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        try:
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
            prompt = await self._prompt.build_prompt_stack(
                session=session,
                context=context,
                request=request,
                retrieval_result=retrieval_result,
            )
            input_transform = await self._pii.transform_input_if_needed(session=session, context=context, text=request.message)
            final_chunks: list[str] = []

            async for token in self._llm.stream_generate(
                prompt=prompt,
                transformed_user_text=input_transform.transformed_text,
                model_override=request.model_override,
                context=context,
            ):
                final_chunks.append(token)
                yield ChatStreamEventToken(type="token", content=token)

            for citation in retrieval_result.citations:
                yield ChatStreamEventCitation(type="citation", citation=citation)

            output_transform = await self._pii.transform_output_if_needed(
                session=session,
                context=context,
                text="".join(final_chunks).strip(),
            )
            persisted = await self._conversations.persist_assistant_message(
                session=session,
                context=context,
                request=request,
                retrieval_result=retrieval_result,
                final_text=output_transform.transformed_text,
                model_used=None,
                tokens_used=None,
            )
            yield ChatStreamEventDone(type="done", message_id=persisted.message_id, trace_id=context.trace_id)
        except Exception as exc:
            yield ChatStreamEventError(type="error", code="chat_stream_failed", message=str(exc))
