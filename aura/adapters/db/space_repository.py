from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import KnowledgeSpace as KnowledgeSpaceModel
from aura.adapters.db.models import SpaceMembership
from aura.domain.contracts import KnowledgeSpace


def _to_contract(space: KnowledgeSpaceModel) -> KnowledgeSpace:
    return KnowledgeSpace.model_validate(space, from_attributes=True)


class SpaceRepository:
    async def create(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        created_by: UUID,
        name: str,
        slug: str,
        space_type: str,
        visibility: str,
        source_access_mode: str,
        embedding_profile_id: UUID,
        retrieval_profile_id: UUID,
        pii_policy_id: UUID | None = None,
        tone_profile_id: UUID | None = None,
        system_instructions: str | None = None,
    ) -> KnowledgeSpace:
        space = KnowledgeSpaceModel(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            space_type=space_type,
            visibility=visibility,
            source_access_mode=source_access_mode,
            embedding_profile_id=embedding_profile_id,
            retrieval_profile_id=retrieval_profile_id,
            pii_policy_id=pii_policy_id,
            tone_profile_id=tone_profile_id,
            system_instructions=system_instructions,
            created_by=created_by,
        )
        session.add(space)
        await session.flush()
        await session.refresh(space)
        return _to_contract(space)

    async def get_by_id(self, session: AsyncSession, space_id: UUID) -> KnowledgeSpace | None:
        result = await session.execute(select(KnowledgeSpaceModel).where(KnowledgeSpaceModel.id == space_id))
        space = result.scalar_one_or_none()
        return None if space is None else _to_contract(space)

    async def list_for_user(self, session: AsyncSession, user_id: UUID) -> list[KnowledgeSpace]:
        result = await session.execute(
            select(KnowledgeSpaceModel)
            .outerjoin(SpaceMembership, SpaceMembership.space_id == KnowledgeSpaceModel.id)
            .where(
                KnowledgeSpaceModel.status == "active",
                or_(
                    SpaceMembership.user_id == user_id,
                    KnowledgeSpaceModel.visibility == "enterprise",
                ),
            )
            .distinct()
            .order_by(KnowledgeSpaceModel.created_at.asc())
        )
        return [_to_contract(space) for space in result.scalars().all()]

    async def update(self, session: AsyncSession, space_id: UUID, updates: dict[str, object]) -> KnowledgeSpace | None:
        result = await session.execute(select(KnowledgeSpaceModel).where(KnowledgeSpaceModel.id == space_id))
        space = result.scalar_one_or_none()
        if space is None:
            return None

        for field, value in updates.items():
            setattr(space, field, value)

        await session.flush()
        await session.refresh(space)
        return _to_contract(space)

    async def archive(self, session: AsyncSession, space_id: UUID) -> KnowledgeSpace | None:
        return await self.update(session, space_id, {"status": "archived"})

    async def add_member(self, session: AsyncSession, space_id: UUID, user_id: UUID, role: str) -> None:
        result = await session.execute(
            select(SpaceMembership).where(
                SpaceMembership.space_id == space_id,
                SpaceMembership.user_id == user_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = SpaceMembership(space_id=space_id, user_id=user_id, role=role)
            session.add(membership)
        else:
            membership.role = role
        await session.flush()

    async def get_membership_role(self, session: AsyncSession, space_id: UUID, user_id: UUID) -> str | None:
        result = await session.execute(
            select(SpaceMembership.role).where(
                SpaceMembership.space_id == space_id,
                SpaceMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
