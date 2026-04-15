from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import agent_service, registry_service, trigger_scheduler_service
from aura.domain.contracts import AgentRunRequest, AgentRunResult, RequestContext


router = APIRouter(prefix="/api/v1", tags=["agents"])


class AgentVersionResponse(BaseModel):
    id: UUID
    name: str
    version: str
    status: str
    agent_type: str
    entrypoint: str


class AgentSummaryResponse(BaseModel):
    agent_id: UUID
    name: str
    slug: str
    description: str | None = None
    status: str


def _to_version_response(version) -> AgentVersionResponse:
    return AgentVersionResponse(
        id=version.id,
        name=version.manifest["name"],
        version=version.version,
        status=version.status,
        agent_type=version.agent_type,
        entrypoint=version.entrypoint,
    )


def _require_admin(context: RequestContext) -> None:
    if set(context.identity.roles).intersection({"admin", "tenant_admin", "platform_admin"}):
        return
    raise HTTPException(status_code=403, detail="Tenant admin role required.")


@router.post("/agents/{name}/run", response_model=AgentRunResult)
async def run_agent(
    name: str,
    payload: dict,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> AgentRunResult:
    request = AgentRunRequest(
        agent_name=name,
        agent_version=payload.get("agent_version"),
        input=payload.get("input", {}),
        conversation_id=payload.get("conversation_id"),
    )
    return await agent_service.run_agent(session=session, request=request, context=context)


@router.get("/agents", response_model=list[AgentSummaryResponse])
async def list_published_agents(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentSummaryResponse]:
    versions = await registry_service.list_versions(session, context.tenant_id)
    latest_by_name: dict[str, AgentSummaryResponse] = {}
    for version in versions:
        if version.status != "published":
            continue
        latest_by_name.setdefault(
            version.name,
            AgentSummaryResponse(
                agent_id=version.id,
                name=version.name,
                slug=version.name.lower().replace(" ", "-"),
                description=version.manifest.get("description"),
                status=version.status,
            ),
        )
    return list(latest_by_name.values())


@router.post("/admin/agents/upload", response_model=AgentVersionResponse)
async def upload_agent(
    manifest: str = Form(...),
    artifact: UploadFile = File(...),
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> AgentVersionResponse:
    _require_admin(context)
    version = await registry_service.upload_and_validate(
        session=session,
        zip_bytes=await artifact.read(),
        manifest_yaml=manifest,
        uploaded_by=context.identity.user_id,
        tenant_id=context.tenant_id,
    )
    return _to_version_response(version)


@router.post("/admin/agents/{agent_version_id}/publish", response_model=AgentVersionResponse)
async def publish_agent(
    agent_version_id: UUID,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> AgentVersionResponse:
    _require_admin(context)
    version = await registry_service.publish(session, agent_version_id)
    for trigger in version.manifest.get("triggers") or []:
        if trigger.get("type") == "cron":
            from aura.domain.contracts import CronTrigger

            await trigger_scheduler_service.register_cron(
                session=session,
                agent_version_id=version.id,
                trigger=CronTrigger.model_validate(trigger),
                tenant_id=context.tenant_id,
            )
        elif trigger.get("type") == "event":
            from aura.adapters.db.models import AgentTriggerRegistration

            session.add(
                AgentTriggerRegistration(
                    tenant_id=context.tenant_id,
                    agent_version_id=version.id,
                    trigger_type="event",
                    trigger_config=trigger,
                    status="active",
                )
            )
    await session.flush()
    return _to_version_response(version)


@router.get("/admin/agents", response_model=list[AgentVersionResponse])
async def list_agents(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentVersionResponse]:
    _require_admin(context)
    versions = await registry_service.list_versions(session, context.tenant_id)
    return [
        AgentVersionResponse(
            id=version.id,
            name=version.name,
            version=version.version,
            status=version.status,
            agent_type=version.agent_type,
            entrypoint=version.entrypoint,
        )
        for version in versions
    ]
