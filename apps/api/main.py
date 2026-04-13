from __future__ import annotations

import asyncio
from typing import Literal
from uuid import UUID

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from apps.api.config import settings
from apps.api.dependencies.auth import get_request_context, identity_middleware
from apps.api.dependencies.db import get_db_session
from apps.api.routers.chat import router as chat_router
from apps.api.routers.datasources import router as datasources_router
from apps.api.routers.spaces import router as spaces_router
from aura.adapters.db.session import AsyncSessionLocal
from aura.domain.contracts import RequestContext, UserIdentity
from aura.domain.models import User


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, Literal["ok", "degraded", "down"]]


class MeResponse(BaseModel):
    identity: UserIdentity
    spaces: list[UUID]
    active_policies: dict[str, UUID]


app = FastAPI(title="AURA API")
app.middleware("http")(identity_middleware)
app.include_router(chat_router)
app.include_router(spaces_router)
app.include_router(datasources_router)


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


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    component_checks = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
        "qdrant": _check_http(str(settings.qdrant_url), ("/readyz", "/healthz", "/")),
        "s3": _check_s3(),
        "litellm": _check_http(str(settings.litellm_base_url), ("/health/readiness", "/health", "/")),
        "okta": _check_okta_jwks(),
        "langfuse": _check_http(str(settings.langfuse_base_url), ("/api/public/health", "/api/health", "/")),
    }
    results = {name: await check for name, check in component_checks.items()}
    status: Literal["ok", "degraded"] = "ok" if all(value == "ok" for value in results.values()) else "degraded"
    return HealthResponse(status=status, components=results)


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
