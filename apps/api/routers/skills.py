from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import skill_service
from aura.domain.contracts import RequestContext


router = APIRouter(prefix="/api/v1", tags=["skills"])


class SkillVersionResponse(BaseModel):
    id: UUID
    name: str
    version: str
    status: str
    entrypoint: str


class SkillRunResponse(BaseModel):
    status: str
    output: dict = Field(default_factory=dict)
    artifacts: list[dict] = Field(default_factory=list)
    error_message: str | None = None
    exit_code: int | None = None
    wall_time_s: float


def _require_admin(context: RequestContext) -> None:
    if set(context.identity.roles).intersection({"admin", "tenant_admin", "platform_admin"}):
        return
    raise HTTPException(status_code=403, detail="Tenant admin role required.")


def _to_skill_response(version) -> SkillVersionResponse:
    return SkillVersionResponse(
        id=version.id,
        name=version.manifest["name"],
        version=version.version,
        status=version.status,
        entrypoint=version.entrypoint,
    )


@router.post("/admin/skills/upload", response_model=SkillVersionResponse)
async def upload_skill(
    manifest: str = Form(...),
    artifact: UploadFile | None = File(default=None),
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> SkillVersionResponse:
    _require_admin(context)
    version = await skill_service.upload_and_validate(
        session=session,
        zip_bytes=await artifact.read() if artifact is not None else None,
        manifest_yaml=manifest,
        uploaded_by=context.identity.user_id,
        tenant_id=context.tenant_id,
    )
    return _to_skill_response(version)


@router.post("/admin/skills/{skill_version_id}/publish", response_model=SkillVersionResponse)
async def publish_skill(
    skill_version_id: UUID,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> SkillVersionResponse:
    _require_admin(context)
    version = await skill_service.publish(session=session, skill_version_id=skill_version_id)
    return _to_skill_response(version)


@router.get("/admin/skills", response_model=list[SkillVersionResponse])
async def list_skills(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[SkillVersionResponse]:
    versions = await skill_service.list_versions(session=session, tenant_id=context.tenant_id)
    return [
        SkillVersionResponse(
            id=version.id,
            name=version.name,
            version=version.version,
            status=version.status,
            entrypoint=version.entrypoint,
        )
        for version in versions
    ]


@router.post("/skills/{name}/run", response_model=SkillRunResponse)
async def run_skill(
    name: str,
    payload: dict,
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
) -> SkillRunResponse:
    result = await skill_service.execute_skill(
        session=session,
        skill_name=name,
        input_obj=dict(payload.get("input") or {}),
        context=context,
    )
    return SkillRunResponse(
        status=result.status,
        output=result.output or {},
        artifacts=[artifact.model_dump() for artifact in result.artifacts],
        error_message=result.error_message,
        exit_code=result.exit_code,
        wall_time_s=result.wall_time_s,
    )
