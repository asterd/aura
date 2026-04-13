from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import Conversation, Message, MessageCitation
from aura.domain.contracts import ChatRequest, Citation, RequestContext, RetrievalResult


@dataclass(slots=True)
class PersistedAssistantMessage:
    conversation_id: UUID
    message_id: UUID


class ConversationService:
    async def persist_assistant_message(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        request: ChatRequest,
        retrieval_result: RetrievalResult,
        final_text: str,
        model_used: str | None = None,
        tokens_used: int | None = None,
    ) -> PersistedAssistantMessage:
        conversation = await self._get_or_create_conversation(session, context, request)
        await self._persist_user_message_if_needed(session, context, conversation.id, request.message)

        assistant_message = Message(
            tenant_id=context.tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=final_text,
            trace_id=context.trace_id,
            model_used=model_used,
            tokens_used=tokens_used,
        )
        session.add(assistant_message)
        await session.flush()

        for citation in retrieval_result.citations:
            session.add(self._build_message_citation(context.tenant_id, assistant_message.id, citation))

        conversation.updated_at = context.now_utc
        await session.flush()
        return PersistedAssistantMessage(conversation_id=conversation.id, message_id=assistant_message.id)

    async def _get_or_create_conversation(
        self,
        session: AsyncSession,
        context: RequestContext,
        request: ChatRequest,
    ) -> Conversation:
        if request.conversation_id is not None:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == request.conversation_id,
                    Conversation.user_id == context.identity.user_id,
                )
            )
            if conversation is not None:
                return conversation

        conversation = Conversation(
            tenant_id=context.tenant_id,
            user_id=context.identity.user_id,
            space_ids=request.space_ids,
            title=(request.message.strip()[:120] or None),
        )
        session.add(conversation)
        await session.flush()
        return conversation

    async def _persist_user_message_if_needed(
        self,
        session: AsyncSession,
        context: RequestContext,
        conversation_id: UUID,
        content: str,
    ) -> None:
        session.add(
            Message(
                tenant_id=context.tenant_id,
                conversation_id=conversation_id,
                role="user",
                content=content,
                trace_id=context.trace_id,
            )
        )
        await session.flush()

    def _build_message_citation(self, tenant_id: UUID, message_id: UUID, citation: Citation) -> MessageCitation:
        return MessageCitation(
            tenant_id=tenant_id,
            message_id=message_id,
            citation_id=citation.citation_id,
            document_id=citation.document_id,
            document_version_id=citation.document_version_id,
            chunk_id=citation.chunk_id,
            score=citation.score,
            snippet=citation.snippet,
        )
