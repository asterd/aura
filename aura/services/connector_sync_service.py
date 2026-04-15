from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from apps.api.config import settings
from aura.adapters.connectors import get_connector
from aura.adapters.connectors.base import ConnectorAclError
from aura.adapters.db.models import Datasource, Document, KnowledgeSpace
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.adapters.qdrant.setup import QdrantChunkStore
from aura.adapters.s3.client import S3Client
from aura.domain.contracts import JobPayload, LoadedDocument
from aura.utils.observability import set_gauge_value
from aura.utils.secrets import EnvSecretStore, SecretStore, resolve_credentials_from_ref


class ConnectorSyncService:
    def __init__(
        self,
        *,
        secret_store: SecretStore | None = None,
        s3_client: S3Client | None = None,
        qdrant_store: QdrantChunkStore | None = None,
    ) -> None:
        self._secret_store = secret_store or EnvSecretStore()
        self._s3 = s3_client or S3Client()
        self._qdrant = qdrant_store or QdrantChunkStore()

    async def enqueue_sync(self, *, payload: JobPayload, datasource_id: UUID) -> UUID:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, payload.tenant_id)
            datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
            if datasource is None:
                raise ValueError(f"Datasource {datasource_id} not found.")
            secret_ref = datasource.credentials_ref

        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        job_id = uuid5(NAMESPACE_URL, f"sync:{datasource_id}")
        try:
            await redis.enqueue_job(
                "connector_sync_job",
                payload.model_dump(mode="json"),
                str(datasource_id),
                secret_ref,
                _job_id=str(job_id),
            )
        finally:
            await redis.aclose()
        return job_id

    async def sync_datasource(self, *, payload: JobPayload, datasource_id: UUID, secret_ref: str) -> None:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, payload.tenant_id)
            datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
            if datasource is None:
                raise ValueError(f"Datasource {datasource_id} not found.")
            space = await session.scalar(select(KnowledgeSpace).where(KnowledgeSpace.id == datasource.space_id))
            if space is None:
                raise ValueError(f"Space {datasource.space_id} not found.")

        connector = get_connector(datasource.connector_type)
        credentials = await resolve_credentials_from_ref(secret_ref, self._secret_store)
        credentials.extra.setdefault("aura_tenant_id", str(payload.tenant_id))

        cursor = datasource.sync_cursor
        partial_failures = 0
        async for loaded in connector.load_documents(datasource_id, credentials, cursor):
            if space.source_access_mode == "source_acl_enforced" and loaded.acl is None and not loaded.is_deleted:
                raise ConnectorAclError("Connector returned no ACL for a source_acl_enforced space.")
            cursor = connector.update_cursor(cursor, loaded)
            try:
                if loaded.is_deleted:
                    await self._mark_deleted(
                        tenant_id=payload.tenant_id,
                        datasource_id=datasource_id,
                        external_id=loaded.external_id,
                    )
                    continue
                await self._upsert_loaded_document(
                    tenant_id=payload.tenant_id,
                    datasource_id=datasource_id,
                    loaded=loaded,
                    payload=payload,
                )
            except ConnectorAclError:
                partial_failures += 1

        await self._mark_sync_completed(
            tenant_id=payload.tenant_id,
            datasource_id=datasource_id,
            cursor=cursor,
            status="partial" if partial_failures else "ok",
        )

    async def mark_auth_error(self, *, tenant_id: UUID, datasource_id: UUID) -> None:
        await self._update_datasource_status(
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            status="auth_error",
            update_last_sync=False,
        )

    async def mark_failure(self, *, tenant_id: UUID, datasource_id: UUID) -> None:
        await self._update_datasource_status(
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            status="failed",
            update_last_sync=False,
        )

    async def refresh_stale_statuses(self, *, tenant_id: UUID | None = None) -> int:
        async with AsyncSessionLocal() as session:
            target_tenant_id = tenant_id
            if target_tenant_id is not None:
                await set_tenant_rls(session, target_tenant_id)
            statement = select(Datasource)
            if target_tenant_id is not None:
                statement = statement.where(Datasource.tenant_id == target_tenant_id)
            datasources = list((await session.execute(statement)).scalars())
            now = datetime.now(UTC)
            stale_count = 0
            for datasource in datasources:
                is_stale = False
                if datasource.last_sync_at is not None:
                    age_s = (now - datasource.last_sync_at).total_seconds()
                    is_stale = age_s > datasource.stale_threshold_s
                if is_stale:
                    datasource.last_sync_status = "stale"
                    datasource.updated_at = now
                    stale_count += 1
                elif datasource.last_sync_status == "stale":
                    datasource.last_sync_status = "ok"
                    datasource.updated_at = now
            await session.commit()
        if target_tenant_id is not None:
            set_gauge_value("aura.datasource.stale_count", stale_count, {"tenant_id": str(target_tenant_id)})
        else:
            set_gauge_value("aura.datasource.stale_count", stale_count)
        return stale_count

    async def _upsert_loaded_document(
        self,
        *,
        tenant_id: UUID,
        datasource_id: UUID,
        loaded: LoadedDocument,
        payload: JobPayload,
    ) -> None:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)
            datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
            if datasource is None:
                raise ValueError(f"Datasource {datasource_id} not found.")
            document = await session.scalar(
                select(Document).where(
                    Document.datasource_id == datasource_id,
                    Document.external_id == loaded.external_id,
                )
            )
            if document is None:
                document = Document(
                    tenant_id=tenant_id,
                    space_id=datasource.space_id,
                    datasource_id=datasource_id,
                    external_id=loaded.external_id,
                    title=loaded.metadata.title,
                    source_path=loaded.metadata.source_path,
                    source_url=loaded.metadata.source_url,
                    content_type=loaded.metadata.content_type,
                    status="discovered",
                )
                session.add(document)
                await session.flush()
            else:
                document.title = loaded.metadata.title
                document.source_path = loaded.metadata.source_path
                document.source_url = loaded.metadata.source_url
                document.content_type = loaded.metadata.content_type
                document.status = "discovered"
                document.updated_at = datetime.now(UTC)

            envelope_key = self._build_connector_cache_key(tenant_id=tenant_id, datasource_id=datasource_id, external_id=loaded.external_id)
            await self._s3.upload_file(
                settings.s3_bucket_name,
                envelope_key,
                loaded.model_dump_json().encode("utf-8"),
                "application/json",
            )
            await session.commit()

        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await redis.enqueue_job(
                "ingest_document_job",
                payload.model_dump(mode="json"),
                str(document.id),
            )
        finally:
            await redis.aclose()

    async def _mark_deleted(self, *, tenant_id: UUID, datasource_id: UUID, external_id: str) -> None:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)
            document = await session.scalar(
                select(Document).where(
                    Document.datasource_id == datasource_id,
                    Document.external_id == external_id,
                )
            )
            if document is None:
                return
            document.status = "deleted"
            document.updated_at = datetime.now(UTC)
            await session.commit()
            await self._qdrant.delete_document_chunks(document.id)

    async def _mark_sync_completed(self, *, tenant_id: UUID, datasource_id: UUID, cursor: str | None, status: str) -> None:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)
            datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
            if datasource is None:
                raise ValueError(f"Datasource {datasource_id} not found.")
            datasource.sync_cursor = cursor
            datasource.last_sync_at = datetime.now(UTC)
            datasource.last_sync_status = status
            datasource.updated_at = datetime.now(UTC)
            await session.commit()
        await self.refresh_stale_statuses(tenant_id=tenant_id)

    async def _update_datasource_status(
        self,
        *,
        tenant_id: UUID,
        datasource_id: UUID,
        status: str,
        update_last_sync: bool,
    ) -> None:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)
            datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
            if datasource is None:
                raise ValueError(f"Datasource {datasource_id} not found.")
            if update_last_sync:
                datasource.last_sync_at = datetime.now(UTC)
            datasource.last_sync_status = status
            datasource.updated_at = datetime.now(UTC)
            await session.commit()
        await self.refresh_stale_statuses(tenant_id=tenant_id)

    def _build_connector_cache_key(self, *, tenant_id: UUID, datasource_id: UUID, external_id: str) -> str:
        digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
        return f"connector-cache/{tenant_id}/{datasource_id}/{digest}.json"
