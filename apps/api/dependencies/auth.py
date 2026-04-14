from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from starlette.responses import JSONResponse
from starlette.responses import Response

from aura.adapters.db.models import Tenant
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import RequestContext, UserIdentity
from aura.services.api_key_service import ApiKeyService
from aura.services.identity import build_request_context, validate_token
from aura.utils.observability import set_current_trace_id


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")
    return token


async def _resolve_api_key_context(request: Request, raw_key: str) -> RequestContext:
    """Costruisce un RequestContext da una API key (Bearer aura_*)."""
    tenant_slug = request.headers.get("X-Tenant-Slug")
    if not tenant_slug:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Tenant-Slug required for API key auth")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
            if not tenant:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown tenant")

            await set_tenant_rls(session, tenant.id)
            api_key_svc = ApiKeyService()
            record = await api_key_svc.resolve(session, raw_key, tenant.id)
            if not record:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired API key")

            identity = UserIdentity(
                user_id=record.user_id if record.user_id else uuid4(),
                tenant_id=tenant.id,
                okta_sub=f"apikey:{record.id}",
                email="service@internal.aura",
                display_name=f"API Key: {record.name}",
                roles=record.scopes,
                is_service_identity=True,
            )
            request_id = str(uuid4())
            trace_id = request.headers.get("X-Trace-Id", str(uuid4()))
            return RequestContext(
                request_id=request_id,
                trace_id=trace_id,
                tenant_id=tenant.id,
                identity=identity,
                now_utc=datetime.now(UTC),
            )


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

        if token.startswith("aura_"):
            # API key authentication
            context = await _resolve_api_key_context(request, token)
        else:
            # JWT authentication
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    claims = await validate_token(session, token)
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
