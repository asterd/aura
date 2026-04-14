from __future__ import annotations

import asyncio
import time
from typing import Literal
from uuid import UUID, uuid4

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from apps.api.config import settings
from apps.api.dependencies.auth import get_request_context, identity_middleware
from apps.api.dependencies.db import get_db_session
from apps.api.routers.agents import router as agents_router
from apps.api.routers.artifacts import router as artifacts_router
from apps.api.routers.chat import router as chat_router
from apps.api.routers.conversations import router as conversations_router
from apps.api.routers.datasources import router as datasources_router
from apps.api.routers.mcp import router as mcp_router
from apps.api.routers.spaces import router as spaces_router
from apps.api.routers.skills import router as skills_router
from apps.api.routers.webhooks import router as webhooks_router
from aura.adapters.sandbox.factory import get_default as get_default_sandbox_provider
from aura.adapters.db.session import AsyncSessionLocal
from aura.adapters.db.models import Group
from aura.adapters.db.models import User as DbUser
from aura.domain.contracts import RequestContext, UserIdentity
from aura.domain.models import User
from aura.utils.observability import (
    get_gauge_value,
    init_otel,
    instrument_fastapi,
    instrument_sqlalchemy,
    record_request_latency,
    set_current_trace_id,
)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, Literal["ok", "degraded", "down"]]
    metrics: dict[str, float] = Field(default_factory=dict)


class MeResponse(BaseModel):
    identity: UserIdentity
    spaces: list[UUID]
    active_policies: dict[str, UUID]


app = FastAPI(title="AURA API")
app.middleware("http")(identity_middleware)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(artifacts_router)
app.include_router(conversations_router)
app.include_router(spaces_router)
app.include_router(datasources_router)
app.include_router(webhooks_router)
app.include_router(skills_router)
app.include_router(mcp_router)

init_otel("aura-api", settings.otlp_endpoint)
instrument_sqlalchemy()
instrument_fastapi(app)
health_engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)


@app.middleware("http")
async def observability_middleware(request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid4())
    request.state.trace_id = trace_id
    set_current_trace_id(trace_id)
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    record_request_latency(
        endpoint=request.url.path,
        method=request.method,
        status=response.status_code,
        latency_ms=(time.perf_counter() - started) * 1000.0,
    )
    return response


async def _check_postgres() -> Literal["ok", "degraded"]:
    try:
        async with AsyncSessionLocal() as session:
            await session.scalar(text("SELECT 1"))
        return "ok"
    except Exception:
        return "degraded"


async def _check_redis() -> Literal["ok", "degraded"]:
    client = redis_from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        pong = await client.ping()
        return "ok" if pong else "degraded"
    except Exception:
        return "degraded"
    finally:
        await client.aclose()


async def _check_http(base_url: str, path_candidates: tuple[str, ...]) -> Literal["ok", "degraded"]:
    timeout = httpx.Timeout(settings.service_check_timeout_s)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        for path in path_candidates:
            try:
                response = await client.get(path)
            except httpx.HTTPError:
                continue
            if response.is_success:
                return "ok"
        return "degraded"


async def _check_s3() -> Literal["ok", "degraded"]:
    def _probe() -> Literal["ok", "degraded"]:
        client = boto3.client(
            "s3",
            endpoint_url=str(settings.s3_endpoint_url),
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            region_name=settings.s3_region,
            use_ssl=settings.s3_secure,
            config=Config(connect_timeout=settings.service_check_timeout_s, read_timeout=settings.service_check_timeout_s),
        )
        try:
            client.head_bucket(Bucket=settings.s3_bucket_name)
            return "ok"
        except (BotoCoreError, ClientError):
            return "degraded"

    return await asyncio.to_thread(_probe)


async def _check_okta_jwks() -> Literal["ok", "degraded"]:
    timeout = httpx.Timeout(settings.service_check_timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(str(settings.okta_jwks_url))
        return "ok" if response.is_success else "degraded"
    except httpx.HTTPError:
        return "degraded"


async def _identity_sync_freshness_seconds() -> float:
    try:
        async with health_engine.connect() as connection:
            user_synced_at = await connection.scalar(select(DbUser.synced_at).order_by(DbUser.synced_at.desc()).limit(1))
            group_synced_at = await connection.scalar(select(Group.synced_at).order_by(Group.synced_at.desc()).limit(1))
    except Exception:
        return get_gauge_value("aura.identity.sync_freshness_s")

    latest_synced_at = max((value for value in (user_synced_at, group_synced_at) if value is not None), default=None)
    if latest_synced_at is None:
        return get_gauge_value("aura.identity.sync_freshness_s")
    return max(0.0, (time.time() - latest_synced_at.timestamp()))


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    sandbox_provider = get_default_sandbox_provider()
    component_checks = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
        "qdrant": _check_http(str(settings.qdrant_url), ("/readyz", "/healthz", "/")),
        "s3": _check_s3(),
        "litellm": _check_http(str(settings.litellm_base_url), ("/health/readiness", "/health", "/")),
        "okta": _check_okta_jwks(),
        "langfuse": _check_http(str(settings.langfuse_base_url), ("/api/public/health", "/api/health", "/")),
        "sandbox": sandbox_provider.health_check(),
    }
    raw_results = {name: await check for name, check in component_checks.items()}
    results = {
        name: value if isinstance(value, str) else ("ok" if value else "down")
        for name, value in raw_results.items()
    }
    status: Literal["ok", "degraded"] = "ok" if all(value == "ok" for value in results.values()) else "degraded"
    identity_sync_freshness = await _identity_sync_freshness_seconds()
    return HealthResponse(
        status=status,
        components=results,
        metrics={
            "aura.datasource.stale_count": get_gauge_value("aura.datasource.stale_count"),
            "aura.identity.sync_freshness_s": identity_sync_freshness,
        },
    )


@app.get(f"{settings.api_prefix}/me", response_model=MeResponse)
async def me(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> MeResponse:
    result = await session.execute(select(User).where(User.id == context.identity.user_id))
    user = result.scalar_one()

    identity = context.identity.model_copy(
        update={
            "email": user.email,
            "display_name": user.display_name,
            "roles": user.roles,
        }
    )
    return MeResponse(identity=identity, spaces=[], active_policies={})
