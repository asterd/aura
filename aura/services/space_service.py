from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import EmbeddingProfile, RetrievalProfile, ToneProfile, User
from aura.adapters.db.space_repository import SpaceCreateData, SpaceRepository
from aura.domain.contracts import KnowledgeSpace, UserIdentity


_ROLE_ORDER = {"reader": 1, "editor": 2, "admin": 3}


@dataclass(slots=True)
class CreateSpaceInput:
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


@dataclass(slots=True)
class UpdateSpaceInput:
    name: str | None = None
    slug: str | None = None
    visibility: str | None = None
    source_access_mode: str | None = None
    embedding_profile_id: UUID | None = None
    retrieval_profile_id: UUID | None = None
    tone_profile_id: UUID | None = None
    system_instructions: str | None = None


@dataclass(slots=True)
class AddMemberInput:
    user_id: UUID
    role: str


def _forbidden(detail: str = "Forbidden.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class SpaceService:
    def __init__(self, repository: SpaceRepository | None = None) -> None:
        self._repository = repository or SpaceRepository()

    async def create_space(self, session: AsyncSession, identity: UserIdentity, data: CreateSpaceInput) -> KnowledgeSpace:
        await self._ensure_user_exists(session, identity.user_id)
        embedding_profile_id = await self._resolve_embedding_profile_id(session, identity.tenant_id, data.embedding_profile_id)
        retrieval_profile_id = await self._resolve_retrieval_profile_id(session, identity.tenant_id, data.retrieval_profile_id)
        tone_profile_id = await self._resolve_tone_profile_id(session, identity.tenant_id, data.tone_profile_id)

        try:
            space = await self._repository.create(
                session,
                SpaceCreateData(
                    tenant_id=identity.tenant_id,
                    name=data.name,
                    slug=data.slug,
                    space_type=data.space_type,
                    visibility=data.visibility,
                    source_access_mode=data.source_access_mode,
                    embedding_profile_id=embedding_profile_id,
                    retrieval_profile_id=retrieval_profile_id,
                    pii_policy_id=data.pii_policy_id,
                    tone_profile_id=tone_profile_id,
                    system_instructions=data.system_instructions,
                ),
                created_by=identity.user_id,
            )
        except IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Space already exists.") from exc

        await self._repository.add_member(session, space.id, identity.user_id, "admin")
        return space

    async def list_spaces(self, session: AsyncSession, identity: UserIdentity) -> list[KnowledgeSpace]:
        return await self._repository.list_for_user(session, identity.user_id)

    async def get_space(self, session: AsyncSession, identity: UserIdentity, space_id: UUID) -> KnowledgeSpace:
        space = await self._load_space(session, space_id)
        if not await self._can_read(session, identity.user_id, space):
            raise _forbidden("You are not allowed to access this space.")
        return space

    async def update_space(
        self,
        session: AsyncSession,
        identity: UserIdentity,
        space_id: UUID,
        data: UpdateSpaceInput,
    ) -> KnowledgeSpace:
        space = await self._authorize_write(session, identity, space_id, minimum_role="editor")
        updates: dict[str, object] = {}

        for field_name in ("name", "slug", "visibility", "source_access_mode", "system_instructions"):
            value = getattr(data, field_name)
            if value is not None:
                updates[field_name] = value

        if data.embedding_profile_id is not None:
            updates["embedding_profile_id"] = await self._resolve_embedding_profile_id(
                session, identity.tenant_id, data.embedding_profile_id
            )
        if data.retrieval_profile_id is not None:
            updates["retrieval_profile_id"] = await self._resolve_retrieval_profile_id(
                session, identity.tenant_id, data.retrieval_profile_id
            )
        if data.tone_profile_id is not None:
            updates["tone_profile_id"] = await self._resolve_tone_profile_id(
                session, identity.tenant_id, data.tone_profile_id
            )

        updated = await self._repository.update(session, space.id, updates)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found.")
        return updated

    async def archive_space(self, session: AsyncSession, identity: UserIdentity, space_id: UUID) -> KnowledgeSpace:
        await self._authorize_write(session, identity, space_id, minimum_role="admin")
        archived = await self._repository.archive(session, space_id)
        if archived is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found.")
        return archived

    async def add_member(
        self,
        session: AsyncSession,
        identity: UserIdentity,
        space_id: UUID,
        data: AddMemberInput,
    ) -> KnowledgeSpace:
        await self._authorize_write(session, identity, space_id, minimum_role="admin")
        await self._ensure_user_exists(session, data.user_id)
        await self._repository.add_member(session, space_id, data.user_id, data.role)
        return await self.get_space(session, identity, space_id)

    async def _load_space(self, session: AsyncSession, space_id: UUID) -> KnowledgeSpace:
        space = await self._repository.get_by_id(session, space_id)
        if space is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found.")
        return space

    async def _authorize_write(
        self,
        session: AsyncSession,
        identity: UserIdentity,
        space_id: UUID,
        *,
        minimum_role: str,
    ) -> KnowledgeSpace:
        space = await self._load_space(session, space_id)
        role = await self._repository.get_membership_role(session, space_id, identity.user_id)
        if role is None or _ROLE_ORDER[role] < _ROLE_ORDER[minimum_role]:
            raise _forbidden("You are not allowed to modify this space.")
        return space

    async def _can_read(self, session: AsyncSession, user_id: UUID, space: KnowledgeSpace) -> bool:
        if space.visibility == "enterprise":
            return True
        role = await self._repository.get_membership_role(session, space.id, user_id)
        return role is not None

    async def _resolve_embedding_profile_id(
        self, session: AsyncSession, tenant_id: UUID, profile_id: UUID | None
    ) -> UUID:
        statement = select(EmbeddingProfile.id).where(EmbeddingProfile.tenant_id == tenant_id)
        if profile_id is None:
            statement = statement.where(EmbeddingProfile.is_default.is_(True))
        else:
            statement = statement.where(EmbeddingProfile.id == profile_id)
        resolved = (await session.execute(statement)).scalar_one_or_none()
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid embedding profile.")
        return resolved

    async def _resolve_retrieval_profile_id(
        self, session: AsyncSession, tenant_id: UUID, profile_id: UUID | None
    ) -> UUID:
        statement = select(RetrievalProfile.id).where(RetrievalProfile.tenant_id == tenant_id)
        if profile_id is None:
            statement = statement.where(RetrievalProfile.is_default.is_(True))
        else:
            statement = statement.where(RetrievalProfile.id == profile_id)
        resolved = (await session.execute(statement)).scalar_one_or_none()
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid retrieval profile.")
        return resolved

    async def _resolve_tone_profile_id(self, session: AsyncSession, tenant_id: UUID, profile_id: UUID | None) -> UUID | None:
        statement = select(ToneProfile.id).where(ToneProfile.tenant_id == tenant_id)
        if profile_id is not None:
            statement = statement.where(ToneProfile.id == profile_id)
        else:
            statement = statement.where(ToneProfile.name == "default")
        return (await session.execute(statement)).scalar_one_or_none()

    async def _ensure_user_exists(self, session: AsyncSession, user_id: UUID) -> None:
        exists = await session.scalar(select(User.id).where(User.id == user_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User not found.")
