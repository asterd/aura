from __future__ import annotations

import asyncio
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models

from apps.api.config import settings


class QdrantChunkStore:
    collection_name = "aura_chunks"
    required_payload_fields = (
        "tenant_id",
        "space_id",
        "document_id",
        "document_version_id",
        "chunk_id",
        "chunk_index",
        "source_id",
        "source_system",
        "source_path",
        "source_url",
        "title",
        "content_type",
        "language",
        "classification",
        "tags",
        "hash",
        "updated_at",
        "source_acl_mode",
        "acl_allow_users",
        "acl_allow_groups",
        "acl_deny_users",
        "acl_deny_groups",
        "acl_inherited",
        "page_number",
        "section_title",
        "char_start",
        "char_end",
    )

    def __init__(self) -> None:
        self._client = QdrantClient(url=str(settings.qdrant_url))

    async def ensure_collection(self, dimensions: int) -> None:
        def _ensure() -> None:
            collections = {collection.name for collection in self._client.get_collections().collections}
            if self.collection_name not in collections:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
                )
            else:
                info = self._client.get_collection(self.collection_name)
                current_size = info.config.params.vectors.size
                if current_size != dimensions:
                    raise ValueError(f"Qdrant collection size mismatch: expected {dimensions}, found {current_size}")

            for field_name in ("tenant_id", "space_id", "source_acl_mode"):
                self._client.create_payload_index(
                    self.collection_name,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )

        await asyncio.to_thread(_ensure)

    async def replace_document_chunks(self, document_id: UUID, points: list[models.PointStruct]) -> None:
        def _replace() -> None:
            self._delete_document_chunks(document_id)
            self._client.upsert(collection_name=self.collection_name, points=points, wait=True)

        await asyncio.to_thread(_replace)

    async def delete_document_chunks(self, document_id: UUID) -> None:
        await asyncio.to_thread(self._delete_document_chunks, document_id)

    def validate_payload(self, payload: dict[str, object]) -> None:
        missing_fields = [field for field in self.required_payload_fields if field not in payload]
        if missing_fields:
            raise ValueError(f"Qdrant payload missing required fields: {', '.join(missing_fields)}")

    def _delete_document_chunks(self, document_id: UUID) -> None:
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
            wait=True,
        )
