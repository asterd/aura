from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import AgentRun
from aura.adapters.db.models import Document
from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import get_conversation_service
from aura.adapters.db.models import Message
from aura.adapters.db.models import MessageAgentRun
from aura.adapters.db.models import MessageCitation
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


class CitationResponse(BaseModel):
    citation_id: str
    document_id: UUID
    title: str
    source_system: str
    source_path: str
    source_url: str | None = None
    page_or_section: str | None = None
    score: float
    snippet: str


class ArtifactRefResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    label: str | None = None
    created_at: datetime


class MessageListItem(BaseModel):
    message_id: UUID
    conversation_id: UUID
    role: str
    content: str
    status: str
    citations: list[CitationResponse]
    artifacts: list[ArtifactRefResponse]
    error: str | None = None
    trace_id: str | None
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]


class MessagePageResponse(BaseModel):
    items: list[MessageListItem]
    next_cursor: str | None = None


def _artifact_type_from_ref(ref: str) -> str:
    lowered = ref.lower()
    if lowered.endswith(".md") or lowered.endswith(".markdown"):
        return "markdown"
    if lowered.endswith(".json"):
        return "json"
    if lowered.endswith(".csv"):
        return "csv"
    if lowered.endswith(".pdf"):
        return "pdf_preview"
    if lowered.endswith(".png") or lowered.endswith(".jpg") or lowered.endswith(".jpeg") or lowered.endswith(".gif") or lowered.endswith(".webp"):
        return "image"
    if "." in lowered.rsplit("/", 1)[-1]:
        return "code"
    return "unknown"


def _artifact_label_from_ref(ref: str) -> str:
    return ref.rsplit("/", 1)[-1] or ref


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


@router.get("/{conversation_id}/messages", response_model=MessagePageResponse)
async def get_messages(
    conversation_id: UUID,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> MessagePageResponse:
    conversation = await conversation_service.get_conversation(
        session=session,
        context=context,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    messages = (
        await session.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()))
    ).scalars().all()
    message_ids = [message.id for message in messages]

    citations_by_message: dict[UUID, list[CitationResponse]] = {}
    artifacts_by_message: dict[UUID, list[ArtifactRefResponse]] = {}

    if message_ids:
        citation_rows = (
            await session.execute(
                select(MessageCitation, Document)
                .join(Document, Document.id == MessageCitation.document_id)
                .where(MessageCitation.message_id.in_(message_ids))
                .order_by(MessageCitation.created_at.asc())
            )
        ).all()
        for citation_row, document in citation_rows:
            citations_by_message.setdefault(citation_row.message_id, []).append(
                CitationResponse(
                    citation_id=citation_row.citation_id,
                    document_id=citation_row.document_id,
                    title=document.title,
                    source_system="document",
                    source_path=document.source_path,
                    source_url=document.source_url,
                    page_or_section=None,
                    score=citation_row.score,
                    snippet=citation_row.snippet,
                )
            )

        artifact_rows = (
            await session.execute(
                select(MessageAgentRun, AgentRun)
                .join(AgentRun, AgentRun.id == MessageAgentRun.agent_run_id)
                .where(MessageAgentRun.message_id.in_(message_ids))
                .order_by(MessageAgentRun.created_at.asc())
            )
        ).all()
        for message_agent_run, agent_run in artifact_rows:
            refs = list(agent_run.artifact_refs or [])
            items = artifacts_by_message.setdefault(message_agent_run.message_id, [])
            for ref in refs:
                items.append(
                    ArtifactRefResponse(
                        artifact_id=ref,
                        artifact_type=_artifact_type_from_ref(ref),
                        label=_artifact_label_from_ref(ref),
                        created_at=agent_run.completed_at or agent_run.started_at,
                    )
                )

    return MessagePageResponse(
        items=[
            MessageListItem(
                message_id=message.id,
                conversation_id=message.conversation_id,
                role="assistant" if message.role == "system" else message.role,
                content=message.content,
                status="DONE",
                citations=citations_by_message.get(message.id, []),
                artifacts=artifacts_by_message.get(message.id, []),
                error=None,
                trace_id=message.trace_id,
                created_at=message.created_at,
            )
            for message in messages
        ],
        next_cursor=None,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> Response:
    deleted = await conversation_service.delete_conversation(
        session=session,
        context=context,
        conversation_id=conversation_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
