from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import get_request_context
from apps.api.dependencies.db import get_db_session
from apps.api.dependencies.services import get_skill_service
from aura.domain.contracts import RequestContext
from aura.services.skill_service import SkillService


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


@router.post("/admin/skills/upload", response_model=SkillVersionResponse)
async def upload_skill(
    manifest: str = Form(...),
    artifact: UploadFile | None = File(default=None),
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    skill_service: SkillService = Depends(get_skill_service),
) -> SkillVersionResponse:
    version = await skill_service.upload_and_validate(
        session=session,
        zip_bytes=await artifact.read() if artifact is not None else None,
        manifest_yaml=manifest,
        uploaded_by=context.identity.user_id,
        tenant_id=context.tenant_id,
    )
    return SkillVersionResponse(
        id=version.id,
        name=version.manifest["name"],
        version=version.version,
        status=version.status,
        entrypoint=version.entrypoint,
    )


@router.post("/admin/skills/{skill_version_id}/publish", response_model=SkillVersionResponse)
async def publish_skill(
    skill_version_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    skill_service: SkillService = Depends(get_skill_service),
) -> SkillVersionResponse:
    version = await skill_service.publish(session=session, skill_version_id=skill_version_id)
    return SkillVersionResponse(
        id=version.id,
        name=version.manifest["name"],
        version=version.version,
        status=version.status,
        entrypoint=version.entrypoint,
    )


@router.get("/admin/skills", response_model=list[SkillVersionResponse])
async def list_skills(
    context: RequestContext = Depends(get_request_context),
    session: AsyncSession = Depends(get_db_session),
    skill_service: SkillService = Depends(get_skill_service),
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
    skill_service: SkillService = Depends(get_skill_service),
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
