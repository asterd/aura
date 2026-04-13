from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select

from aura.adapters.db.models import Group, User, UserGroupMembership
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import IdentitySyncResult
from aura.utils.observability import set_gauge_value


@dataclass(slots=True)
class DirectoryUser:
    okta_sub: str
    email: str
    display_name: str | None = None
    roles: list[str] = field(default_factory=list)
    group_external_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DirectoryGroup:
    external_id: str
    display_name: str


@dataclass(slots=True)
class DirectorySnapshot:
    users: list[DirectoryUser]
    groups: list[DirectoryGroup]
    partial_failures: int = 0


class DirectoryProvider(Protocol):
    async def fetch_snapshot(self, tenant_id: UUID) -> DirectorySnapshot: ...


class OktaDirectoryProvider:
    async def fetch_snapshot(self, tenant_id: UUID) -> DirectorySnapshot:
        raise NotImplementedError("Okta Management sync is not configured in this environment.")


class StaticDirectoryProvider:
    def __init__(self, snapshot: DirectorySnapshot) -> None:
        self._snapshot = snapshot

    async def fetch_snapshot(self, tenant_id: UUID) -> DirectorySnapshot:
        return self._snapshot


class IdentitySyncService:
    def __init__(self, *, provider: DirectoryProvider | None = None) -> None:
        self._provider = provider or OktaDirectoryProvider()

    async def sync_tenant(self, *, tenant_id: UUID) -> IdentitySyncResult:
        snapshot = await self._provider.fetch_snapshot(tenant_id)
        now = datetime.now(UTC)
        seen_group_external_ids = {group.external_id for group in snapshot.groups}
        seen_user_subs = {user.okta_sub for user in snapshot.users}

        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)

            existing_groups = list((await session.execute(select(Group).where(Group.tenant_id == tenant_id))).scalars())
            existing_users = list((await session.execute(select(User).where(User.tenant_id == tenant_id))).scalars())

            groups_by_external_id: dict[str, Group] = {}
            groups_updated = 0
            for directory_group in snapshot.groups:
                group = await session.scalar(
                    select(Group).where(
                        Group.tenant_id == tenant_id,
                        Group.external_id == directory_group.external_id,
                    )
                )
                if group is None:
                    group = Group(
                        tenant_id=tenant_id,
                        external_id=directory_group.external_id,
                        display_name=directory_group.display_name,
                        synced_at=now,
                    )
                    session.add(group)
                    await session.flush()
                else:
                    group.display_name = directory_group.display_name
                    group.synced_at = now
                groups_by_external_id[directory_group.external_id] = group
                groups_updated += 1

            for group in existing_groups:
                if group.external_id not in seen_group_external_ids:
                    group.synced_at = None

            users_updated = 0
            unmapped_users = 0
            for directory_user in snapshot.users:
                user = await session.scalar(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.okta_sub == directory_user.okta_sub,
                    )
                )
                if user is None:
                    user = User(
                        tenant_id=tenant_id,
                        okta_sub=directory_user.okta_sub,
                        email=directory_user.email,
                        display_name=directory_user.display_name,
                        roles=directory_user.roles,
                        synced_at=now,
                        updated_at=now,
                    )
                    session.add(user)
                    await session.flush()
                else:
                    user.email = directory_user.email
                    user.display_name = directory_user.display_name
                    user.roles = directory_user.roles
                    user.synced_at = now
                    user.updated_at = now

                for external_group_id in directory_user.group_external_ids:
                    group = groups_by_external_id.get(external_group_id)
                    if group is None:
                        unmapped_users += 1
                        continue
                    membership = await session.scalar(
                        select(UserGroupMembership).where(
                            UserGroupMembership.user_id == user.id,
                            UserGroupMembership.group_id == group.id,
                        )
                    )
                    if membership is None:
                        session.add(UserGroupMembership(user_id=user.id, group_id=group.id))
                users_updated += 1

            for user in existing_users:
                if user.okta_sub not in seen_user_subs:
                    user.synced_at = None
                    user.updated_at = now

            await session.commit()

        set_gauge_value("aura.identity.sync_freshness_s", 0.0)
        return IdentitySyncResult(
            tenant_id=tenant_id,
            users_seen=len(snapshot.users),
            users_updated=users_updated,
            groups_seen=len(snapshot.groups),
            groups_updated=groups_updated,
            unmapped_users=unmapped_users,
            partial_failures=snapshot.partial_failures,
            completed_at=now,
        )
