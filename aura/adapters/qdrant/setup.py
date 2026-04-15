from __future__ import annotations

import asyncio
import time
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
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

    def _is_retryable_error(self, exc: UnexpectedResponse) -> bool:
        return getattr(exc, "status_code", None) in {404, 500}

    def _wait_for_collection(self) -> models.CollectionInfo:
        last_error: UnexpectedResponse | None = None
        for _ in range(20):
            try:
                return self._client.get_collection(self.collection_name)
            except UnexpectedResponse as exc:
                if not self._is_retryable_error(exc):
                    raise
                last_error = exc
                time.sleep(0.2)
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Qdrant collection {self.collection_name} not available")

    def _vector_size(self, info: models.CollectionInfo) -> int:
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            first = next(iter(vectors.values()), None)
            if first is None:
                raise ValueError("Qdrant collection has no vector configuration.")
            return int(first.size)
        if vectors is None:
            raise ValueError("Qdrant collection vector configuration is missing.")
        return int(vectors.size)

    async def ensure_collection(self, dimensions: int) -> None:
        def _ensure() -> None:
            try:
                info = self._client.get_collection(self.collection_name)
            except UnexpectedResponse as exc:
                if getattr(exc, "status_code", None) != 404:
                    raise
                try:
                    self._client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
                    )
                except UnexpectedResponse as create_exc:
                    if getattr(create_exc, "status_code", None) != 409:
                        raise
                info = self._wait_for_collection()

            current_size = self._vector_size(info)
            if current_size != dimensions:
                raise ValueError(f"Qdrant collection size mismatch: expected {dimensions}, found {current_size}")

            for field_name in ("tenant_id", "space_id", "source_acl_mode"):
                last_error: UnexpectedResponse | None = None
                for _ in range(20):
                    try:
                        self._client.create_payload_index(
                            self.collection_name,
                            field_name=field_name,
                            field_schema=models.PayloadSchemaType.KEYWORD,
                            wait=True,
                        )
                        break
                    except UnexpectedResponse as exc:
                        status_code = getattr(exc, "status_code", None)
                        if status_code == 409:
                            break
                        if not self._is_retryable_error(exc):
                            raise
                        last_error = exc
                        time.sleep(0.2)
                else:
                    if last_error is not None:
                        raise last_error

        await asyncio.to_thread(_ensure)

    async def replace_document_chunks(self, document_id: UUID, points: list[models.PointStruct]) -> None:
        def _replace() -> None:
            self._delete_document_chunks(document_id)
            last_error: UnexpectedResponse | None = None
            for _ in range(20):
                try:
                    self._client.upsert(collection_name=self.collection_name, points=points, wait=True)
                    self._wait_for_collection()
                    return
                except UnexpectedResponse as exc:
                    if not self._is_retryable_error(exc):
                        raise
                    last_error = exc
                    time.sleep(0.2)
            if last_error is not None:
                raise last_error

        await asyncio.to_thread(_replace)

    async def delete_document_chunks(self, document_id: UUID) -> None:
        await asyncio.to_thread(self._delete_document_chunks, document_id)

    def validate_payload(self, payload: dict[str, object]) -> None:
        missing_fields = [field for field in self.required_payload_fields if field not in payload]
        if missing_fields:
            raise ValueError(f"Qdrant payload missing required fields: {', '.join(missing_fields)}")

    def _delete_document_chunks(self, document_id: UUID) -> None:
        last_error: UnexpectedResponse | None = None
        for _ in range(20):
            try:
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
                return
            except UnexpectedResponse as exc:
                if getattr(exc, "status_code", None) == 404:
                    return
                if not self._is_retryable_error(exc):
                    raise
                last_error = exc
                time.sleep(0.2)
        if last_error is not None:
            raise last_error
