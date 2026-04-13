from __future__ import annotations

import asyncio
from typing import Literal

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI
from pydantic import BaseModel
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text

from apps.api.config import settings
from aura.adapters.db.session import AsyncSessionLocal


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, Literal["ok", "degraded"]]


app = FastAPI(title="AURA API")


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


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    component_checks = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
        "qdrant": _check_http(str(settings.qdrant_url), ("/readyz", "/healthz", "/")),
        "s3": _check_s3(),
        "litellm": _check_http(str(settings.litellm_base_url), ("/health/readiness", "/health", "/")),
        "langfuse": _check_http(str(settings.langfuse_base_url), ("/api/public/health", "/api/health", "/")),
    }
    results = {name: await check for name, check in component_checks.items()}
    status: Literal["ok", "degraded"] = "ok" if all(value == "ok" for value in results.values()) else "degraded"
    return HealthResponse(status=status, components=results)
