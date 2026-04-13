from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import get_conversation_service
from aura.adapters.db.models import Message
from aura.domain.contracts import RequestContext
from aura.services.conversation_service import ConversationService


router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    id: UUID
    title: str | None
    space_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    id: UUID
    role: str
    content: str
    trace_id: str | None
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationSummary]:
    conversations = await conversation_service.list_conversations(session=session, context=context)
    return [
        ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            space_ids=conversation.space_ids,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation in conversations
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetail:
    conversation = await conversation_service.get_conversation(session=session, context=context, conversation_id=conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    messages = (
        await session.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()))
    ).scalars().all()
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        space_ids=conversation.space_ids,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ConversationMessage(
                id=message.id,
                role=message.role,
                content=message.content,
                trace_id=message.trace_id,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )
