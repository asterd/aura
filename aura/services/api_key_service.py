from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aura.adapters.db.models import ApiKey


class ApiKeyService:
    PREFIX = "aura_"
    KEY_BYTES = 32

    def generate_raw_key(self) -> str:
        """Genera una API key raw — mostrata UNA VOLTA all'utente."""
        return self.PREFIX + secrets.token_hex(self.KEY_BYTES)

    def hash_key(self, raw_key: str) -> str:
        """SHA-256 dell'API key per storage sicuro."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def create(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        name: str,
        scopes: list[str],
        expires_at: datetime | None,
    ) -> tuple[ApiKey, str]:
        """Crea una nuova API key. Restituisce (record, raw_key)."""
        raw_key = self.generate_raw_key()
        key_hash = self.hash_key(raw_key)
        prefix = raw_key[: len(self.PREFIX) + 8]

        record = ApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            scopes=scopes,
            expires_at=expires_at,
        )
        session.add(record)
        await session.flush()
        return record, raw_key

    async def resolve(
        self,
        session: AsyncSession,
        raw_key: str,
        tenant_id: UUID,
    ) -> ApiKey | None:
        """Verifica una API key. Restituisce il record se valida e attiva."""
        key_hash = self.hash_key(raw_key)
        now = datetime.now(UTC)
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.tenant_id == tenant_id,
                ApiKey.revoked_at.is_(None),
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        if record.expires_at and record.expires_at < now:
            return None
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == record.id)
            .values(last_used_at=now)
        )
        return record

    async def revoke(self, session: AsyncSession, key_id: UUID, tenant_id: UUID) -> bool:
        result = await session.execute(
            update(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id, ApiKey.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
            .returning(ApiKey.id)
        )
        return result.scalar_one_or_none() is not None

    async def list_keys(self, session: AsyncSession, tenant_id: UUID) -> list[ApiKey]:
        result = await session.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars())
