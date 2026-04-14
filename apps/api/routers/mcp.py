from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import get_mcp_server_service
from aura.domain.contracts import RequestContext
from aura.services.mcp_server_service import McpServerService


router = APIRouter(tags=["mcp"])


@router.get("/mcp/v1/sse", response_model=None)
async def open_mcp_stream(
    request: Request,
    context: RequestContext = Depends(get_request_context),
    mcp_service: McpServerService = Depends(get_mcp_server_service),
) -> StreamingResponse | dict[str, str]:
    session_id = await mcp_service.open_session(context)
    message_endpoint = f"/mcp/v1/sse/messages/{session_id}"
    if request.headers.get("x-aura-mcp-bootstrap") == "1":
        return {"message_endpoint": message_endpoint}

    async def _stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in mcp_service.stream(session_id):
                yield chunk
        finally:
            await mcp_service.close_session(session_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"x-mcp-message-endpoint": message_endpoint},
    )


@router.post("/mcp/v1/sse/messages/{session_id}", status_code=202)
async def post_mcp_message(
    session_id: str,
    payload: dict,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    mcp_service: McpServerService = Depends(get_mcp_server_service),
) -> dict:
    try:
        response = await mcp_service.handle_message(session_id=session_id, session=session, context=context, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return response or {"accepted": True}
