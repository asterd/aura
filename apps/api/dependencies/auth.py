from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, Request, status
from starlette.responses import JSONResponse
from starlette.responses import Response

from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import RequestContext, UserIdentity
from aura.services.identity import build_request_context, validate_jwt
from aura.utils.observability import set_current_trace_id


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")
    return token


async def identity_middleware(request: Request, call_next) -> Response:
    request.state.identity = None
    request.state.context = None
    request.state.tenant_id = None
    request.state.request_id = None
    request.state.trace_id = request.headers.get("X-Trace-Id")

    try:
        token = _extract_bearer_token(request)
        if token is None:
            return await call_next(request)

        claims = await validate_jwt(token)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await set_tenant_rls(session, claims.tenant_id)
                context = await build_request_context(
                    session,
                    claims=claims,
                    request_id=str(uuid4()),
                    trace_id=request.headers.get("X-Trace-Id", str(uuid4())),
                )
            request.state.identity = context.identity
            request.state.context = context
            request.state.tenant_id = context.tenant_id
            request.state.request_id = context.request_id
            request.state.trace_id = context.trace_id
            set_current_trace_id(context.trace_id)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


def require_identity(request: Request) -> UserIdentity:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return identity


def get_request_context(request: Request) -> RequestContext:
    context = getattr(request.state, "context", None)
    if context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return context
