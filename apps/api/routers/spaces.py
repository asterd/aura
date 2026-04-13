from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies.auth import require_identity
from apps.api.dependencies.db import get_db_session
from aura.domain.contracts import KnowledgeSpace, UserIdentity
from aura.services.space_service import AddMemberInput, CreateSpaceInput, SpaceService, UpdateSpaceInput


router = APIRouter(prefix="/api/v1/spaces", tags=["spaces"])
space_service = SpaceService()


class CreateSpaceRequest(BaseModel):
    name: str
    slug: str
    space_type: str
    visibility: str
    source_access_mode: str
    embedding_profile_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    pii_policy_id: UUID | None = None
    tone_profile_id: UUID | None = None
    system_instructions: str | None = None


class UpdateSpaceRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    visibility: str | None = None
    source_access_mode: str | None = None
    embedding_profile_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    tone_profile_id: UUID | None = None
    system_instructions: str | None = None


class AddMemberRequest(BaseModel):
    user_id: UUID
    role: str


@router.post("", response_model=KnowledgeSpace, status_code=status.HTTP_201_CREATED)
async def create_space(
    payload: CreateSpaceRequest,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeSpace:
    return await space_service.create_space(session, identity, CreateSpaceInput(**payload.model_dump()))


@router.get("", response_model=list[KnowledgeSpace])
async def list_spaces(
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> list[KnowledgeSpace]:
    return await space_service.list_spaces(session, identity)


@router.get("/{space_id}", response_model=KnowledgeSpace)
async def get_space(
    space_id: UUID,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeSpace:
    return await space_service.get_space(session, identity, space_id)


@router.patch("/{space_id}", response_model=KnowledgeSpace)
async def update_space(
    space_id: UUID,
    payload: UpdateSpaceRequest,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeSpace:
    return await space_service.update_space(session, identity, space_id, UpdateSpaceInput(**payload.model_dump()))


@router.delete("/{space_id}", response_model=KnowledgeSpace)
async def archive_space(
    space_id: UUID,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeSpace:
    return await space_service.archive_space(session, identity, space_id)


@router.post("/{space_id}/members", response_model=KnowledgeSpace)
async def add_member(
    space_id: UUID,
    payload: AddMemberRequest,
    identity: UserIdentity = Depends(require_identity),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeSpace:
    return await space_service.add_member(session, identity, space_id, AddMemberInput(**payload.model_dump()))
