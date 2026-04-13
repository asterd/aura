from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5

from redis.asyncio import from_url as redis_from_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import Datasource, Document, DocumentVersion, EmbeddingProfile, KnowledgeSpace
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.adapters.embeddings.litellm import LiteLLMEmbeddingClient
from aura.adapters.qdrant.setup import QdrantChunkStore
from aura.adapters.s3.client import S3Client
from aura.domain.contracts import JobPayload


@dataclass(slots=True)
class ParsedChunk:
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    page_number: int | None = None
    section_title: str | None = None


class IngestionService:
    def __init__(
        self,
        *,
        s3_client: S3Client | None = None,
        qdrant_store: QdrantChunkStore | None = None,
        embedding_client: LiteLLMEmbeddingClient | None = None,
    ) -> None:
        self._s3 = s3_client or S3Client()
        self._qdrant = qdrant_store or QdrantChunkStore()
        self._embeddings = embedding_client or LiteLLMEmbeddingClient()

    async def ingest_document(self, *, payload: JobPayload, document_id: UUID) -> None:
        redis = redis_from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        lock = redis.lock(f"lock:ingest:{document_id}", timeout=300, blocking=False)
        acquired = await lock.acquire()
        if not acquired:
            await redis.aclose()
            return

        try:
            async with AsyncSessionLocal() as session:
                await set_tenant_rls(session, payload.tenant_id)
                document, datasource, space, embedding_profile = await self._load_document_bundle(session, document_id)

                original_key = self._require_ref(document.external_id)
                original_bytes = await self._s3.download_file(settings.s3_bucket_name, original_key)
                await self._persist_document_status(session, payload.tenant_id, document, "fetched")

                canonical_text = await self._parse_document(document.source_path, document.content_type, original_bytes)
                await self._persist_document_status(session, payload.tenant_id, document, "parsed")

                canonical_bytes = canonical_text.encode("utf-8")
                version_hash = hashlib.sha256(canonical_bytes).hexdigest()
                payload.job_key = f"ingest:{document.id}:{version_hash}"
                existing_version = await self._find_existing_version(session, document.id, version_hash)
                if existing_version is not None:
                    document.current_version_id = existing_version.id
                    await self._persist_document_status(session, payload.tenant_id, document, "active")
                    return

                canonical_key = f"canonical/{payload.tenant_id}/{document.id}/{version_hash}.txt"
                await self._s3.upload_file(settings.s3_bucket_name, canonical_key, canonical_bytes, "text/plain")
                version = DocumentVersion(
                    document_id=document.id,
                    tenant_id=payload.tenant_id,
                    version_hash=version_hash,
                    s3_canonical_ref=canonical_key,
                    s3_original_ref=original_key,
                )
                session.add(version)
                await session.flush()
                await self._persist_document_status(session, payload.tenant_id, document, "canonicalized")

                chunks = self._split_text(canonical_text, embedding_profile.chunk_size, embedding_profile.chunk_overlap)
                vectors = await self._embeddings.embed_texts(
                    model=embedding_profile.litellm_model,
                    texts=[chunk.text for chunk in chunks],
                    dimensions=embedding_profile.dimensions,
                    batch_size=embedding_profile.batch_size,
                )
                await self._qdrant.ensure_collection(embedding_profile.dimensions)

                updated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                points = []
                for chunk, vector in zip(chunks, vectors, strict=True):
                    payload_dict = self._build_qdrant_payload(
                        document=document,
                        version=version,
                        datasource=datasource,
                        space=space,
                        chunk=chunk,
                        version_hash=version_hash,
                        updated_at=updated_at,
                    )
                    self._qdrant.validate_payload(payload_dict)
                    point_id = str(uuid5(NAMESPACE_URL, f"{version.id}:{chunk.chunk_index}:{chunk.char_start}:{chunk.char_end}"))
                    points.append(
                        {
                            "id": point_id,
                            "vector": vector,
                            "payload": payload_dict,
                        }
                    )

                from qdrant_client.http.models import PointStruct

                await self._qdrant.replace_document_chunks(
                    document.id,
                    [PointStruct(id=point["id"], vector=point["vector"], payload=point["payload"]) for point in points],
                )

                version.chunk_count = len(chunks)
                version.indexed_at = datetime.now(UTC)
                document.current_version_id = version.id
                await self._persist_document_status(session, payload.tenant_id, document, "indexed")
                await self._persist_document_status(session, payload.tenant_id, document, "active")
        except Exception:
            await self._mark_document_error(payload.tenant_id, document_id)
            raise
        finally:
            if acquired:
                await lock.release()
            await redis.aclose()

    async def _load_document_bundle(
        self, session: AsyncSession, document_id: UUID
    ) -> tuple[Document, Datasource, KnowledgeSpace, EmbeddingProfile]:
        document = await session.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            raise ValueError(f"Document {document_id} not found.")
        datasource = await session.scalar(select(Datasource).where(Datasource.id == document.datasource_id))
        if datasource is None:
            raise ValueError(f"Datasource for document {document_id} not found.")
        space = await session.scalar(select(KnowledgeSpace).where(KnowledgeSpace.id == document.space_id))
        if space is None:
            raise ValueError(f"Space for document {document_id} not found.")
        embedding_profile = await session.scalar(select(EmbeddingProfile).where(EmbeddingProfile.id == space.embedding_profile_id))
        if embedding_profile is None:
            raise ValueError(f"Embedding profile for space {space.id} not found.")
        return document, datasource, space, embedding_profile

    async def _find_existing_version(self, session: AsyncSession, document_id: UUID, version_hash: str) -> DocumentVersion | None:
        return await session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_hash == version_hash,
            )
        )

    async def _persist_document_status(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        document: Document,
        status: str,
    ) -> None:
        document.status = status
        document.updated_at = datetime.now(UTC)
        await session.commit()
        await set_tenant_rls(session, tenant_id)

    async def _mark_document_error(self, tenant_id: UUID, document_id: UUID) -> None:
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)
            document = await session.scalar(select(Document).where(Document.id == document_id))
            if document is None:
                return
            document.status = "error"
            document.updated_at = datetime.now(UTC)
            await session.commit()

    async def _parse_document(self, source_path: str, content_type: str, data: bytes) -> str:
        suffix = Path(source_path).suffix.lower()
        try:
            if suffix == ".pdf" or content_type == "application/pdf":
                from llama_index.readers.file import PDFReader

                import tempfile

                with tempfile.TemporaryDirectory() as tmp_dir:
                    pdf_path = Path(tmp_dir) / "upload.pdf"
                    pdf_path.write_bytes(data)
                    docs = PDFReader().load_data(file=pdf_path)
                text = "\n".join(doc.text for doc in docs if getattr(doc, "text", None))
                return self._canonicalize_text(text)

            return self._canonicalize_text(data.decode("utf-8"))
        except ImportError:
            return self._canonicalize_text(self._fallback_extract_text(source_path, data))
        except UnicodeDecodeError:
            return self._canonicalize_text(self._fallback_extract_text(source_path, data))

    def _fallback_extract_text(self, source_path: str, data: bytes) -> str:
        if Path(source_path).suffix.lower() == ".pdf":
            decoded = data.decode("latin-1", errors="ignore")
            matches = re.findall(r"\((.*?)\)\s*Tj", decoded, flags=re.DOTALL)
            if matches:
                return " ".join(match.replace("\\)", ")").replace("\\(", "(") for match in matches)
        return data.decode("utf-8", errors="ignore")

    def _canonicalize_text(self, raw_text: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
        canonical = "\n".join(line for line in lines if line)
        if not canonical:
            raise ValueError("Parsed document is empty.")
        return canonical

    def _split_text(self, text: str, chunk_size: int, chunk_overlap: int) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        cursor = 0
        chunk_index = 0
        text_len = len(text)
        while cursor < text_len:
            chunk_end = min(cursor + chunk_size, text_len)
            chunk_text = text[cursor:chunk_end].strip()
            if chunk_text:
                chunks.append(
                    ParsedChunk(
                        text=chunk_text,
                        chunk_index=chunk_index,
                        char_start=cursor,
                        char_end=chunk_end,
                    )
                )
                chunk_index += 1
            if chunk_end >= text_len:
                break
            cursor = max(chunk_end - chunk_overlap, cursor + 1)
        if not chunks:
            raise ValueError("No chunks generated for document.")
        return chunks

    def _build_qdrant_payload(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        datasource: Datasource,
        space: KnowledgeSpace,
        chunk: ParsedChunk,
        version_hash: str,
        updated_at: str,
    ) -> dict[str, object]:
        chunk_id = str(uuid5(NAMESPACE_URL, f"{version.id}:{chunk.chunk_index}:{chunk.char_start}:{chunk.char_end}"))
        return {
            "tenant_id": str(document.tenant_id),
            "space_id": str(document.space_id),
            "document_id": str(document.id),
            "document_version_id": str(version.id),
            "chunk_id": chunk_id,
            "chunk_index": chunk.chunk_index,
            "source_id": str(datasource.id),
            "source_system": datasource.connector_type,
            "source_path": document.source_path,
            "source_url": document.source_url,
            "title": document.title,
            "content_type": document.content_type,
            "language": None,
            "classification": None,
            "tags": [],
            "hash": f"sha256:{version_hash}",
            "updated_at": updated_at,
            "source_acl_mode": "space_acl_only" if datasource.connector_type == "file_upload" else space.source_access_mode,
            "acl_allow_users": [],
            "acl_allow_groups": [],
            "acl_deny_users": [],
            "acl_deny_groups": [],
            "acl_inherited": True,
            "page_number": chunk.page_number,
            "section_title": chunk.section_title,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
        }

    def _require_ref(self, ref: str | None) -> str:
        if not ref:
            raise ValueError("Missing S3 reference.")
        return ref
