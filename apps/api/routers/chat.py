from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import (
    agent_chat_service,
    chat_service,
    conversation_service,
    retrieval_service,
    policy_service,
)
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import ChatRequest, ChatResponse, RequestContext, RetrievalRequest, RetrievalResult


router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class AvailableModelsResponse(BaseModel):
    default_model: str
    allowed_models: list[str]


@router.get("/models", response_model=AvailableModelsResponse)
async def get_available_models(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> AvailableModelsResponse:
    policy = await policy_service.resolve_model_policy(session=session, entity=None, context=context)
    return AvailableModelsResponse(
        default_model=policy.default_model,
        allowed_models=policy.allowed_models,
    )


def _should_invoke_agent_flow(request: ChatRequest) -> bool:
    return bool(request.invoked_agents or request.active_agent_ids or "@" in request.message)


class RetrieveApiRequest(BaseModel):
    query: str
    space_ids: list[UUID]
    conversation_id: UUID | None = None
    retrieval_profile_id: UUID | None = None


class RetrieveApiResponse(BaseModel):
    result: RetrievalResult
    trace_id: str


@router.post("/retrieve", response_model=RetrieveApiResponse)
async def retrieve(
    payload: RetrievalRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> RetrieveApiResponse:
    result = await retrieval_service.retrieve(
        session=session,
        request=payload,
        context=context,
    )
    return RetrieveApiResponse(result=result, trace_id=context.trace_id)


@router.post("/respond", response_model=ChatResponse)
async def respond(
    payload: ChatRequest,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    if _should_invoke_agent_flow(payload):
        history = await conversation_service.get_history(
            session=session,
            context=context,
            conversation_id=payload.conversation_id,
        )
        return await agent_chat_service.respond(session=session, ctx=context, request=payload, history=history)
    return await chat_service.respond(session=session, request=payload, context=context)


@router.post("/stream")
async def stream(
    payload: ChatRequest,
    context: RequestContext = Depends(get_request_context),
) -> StreamingResponse:
    async def event_source():
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await set_tenant_rls(session, context.tenant_id)
                if _should_invoke_agent_flow(payload):
                    history = await conversation_service.get_history(
                        session=session,
                        context=context,
                        conversation_id=payload.conversation_id,
                    )
                    event_iter = agent_chat_service.respond_stream(
                        session=session,
                        ctx=context,
                        request=payload,
                        history=history,
                    )
                else:
                    event_iter = chat_service.respond_stream(
                        session=session,
                        request=payload,
                        context=context,
                    )
                async for event in event_iter:
                    yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
