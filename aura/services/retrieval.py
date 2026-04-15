from __future__ import annotations

import asyncio
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import time
from uuid import UUID

from fastapi import HTTPException, status
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http import models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import EmbeddingProfile, RetrievalProfile
from aura.adapters.embeddings.litellm import LiteLLMEmbeddingClient
from aura.adapters.qdrant.filter_builder import build_retrieval_filter
from aura.domain.contracts import Citation, KnowledgeSpace, LlmTaskType, RequestContext, RetrievalRequest, RetrievalResult
from aura.services.cost_management_service import CostManagementService, UsageContext
from aura.services.llm_provider_service import LlmProviderService
from aura.services.space_service import SpaceService
from aura.utils.observability import record_retrieval_latency


@dataclass(slots=True)
class _Candidate:
    point_id: str
    payload: dict[str, object]
    score: float


class RetrievalService:
    def __init__(
        self,
        *,
        embedding_client: LiteLLMEmbeddingClient | None = None,
        qdrant_client: QdrantClient | None = None,
        space_service: SpaceService | None = None,
        llm_provider_service: LlmProviderService | None = None,
        cost_management_service: CostManagementService | None = None,
    ) -> None:
        self._embeddings = embedding_client or LiteLLMEmbeddingClient()
        self._qdrant = qdrant_client or QdrantClient(url=str(settings.qdrant_url))
        self._spaces = space_service or SpaceService()
        self._providers = llm_provider_service or LlmProviderService()
        self._costs = cost_management_service or CostManagementService()

    async def retrieve(
        self,
        *,
        session: AsyncSession,
        request: RetrievalRequest,
        context: RequestContext,
    ) -> RetrievalResult:
        if not request.space_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one space is required.")
        authorized_spaces = [await self._spaces.require_membership(session, context.identity, space_id) for space_id in request.space_ids]
        retrieval_profile = await self._resolve_retrieval_profile(session, context.tenant_id, authorized_spaces, request)
        filter_obj = build_retrieval_filter(
            tenant_id=context.tenant_id,
            space_ids=[space.id for space in authorized_spaces],
            identity=context.identity,
            acl_mode="source_acl_enforced" if any(space.source_access_mode == "source_acl_enforced" for space in authorized_spaces) else "space_acl_only",
        )
        query_text = request.query
        embedding_profile = await self._resolve_embedding_profile(session, authorized_spaces[0].embedding_profile_id)
        runtime = await self._providers.resolve_model(
            session=session,
            tenant_id=context.tenant_id,
            requested_model=embedding_profile.litellm_model,
            task_type=LlmTaskType.embedding,
        )
        input_tokens = max(1, len(query_text.split()))
        usage_context = UsageContext(
            provider_id=runtime.provider_id,
            provider_key=runtime.provider_key,
            model_name=runtime.runtime_model_name,
            task_type=LlmTaskType.embedding,
            space_id=authorized_spaces[0].id,
            conversation_id=request.conversation_id,
            credential_id=runtime.credential_id,
        )
        projected_input_cost = self._costs.estimate_cost(
            input_tokens=input_tokens,
            output_tokens=0,
            input_cost_per_1k=runtime.input_cost_per_1k,
            output_cost_per_1k=Decimal("0"),
        )
        await self._costs.check_budget(
            session=session,
            context=context,
            usage=usage_context,
            projected_cost_usd=projected_input_cost,
        )
        started = time.perf_counter()
        try:
            candidates = await self._hybrid_search(
                query=query_text,
                embedding_profile=embedding_profile,
                retrieval_profile=retrieval_profile,
                filter_obj=filter_obj,
                runtime=runtime,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Retrieval backend unavailable.",
            ) from exc
        reranked = self._rerank_candidates(query_text, candidates, retrieval_profile.reranker)
        selected = [candidate for candidate in reranked if candidate.score >= retrieval_profile.score_threshold][: retrieval_profile.rerank_top_k]
        record_retrieval_latency(
            space_id=str(authorized_spaces[0].id),
            reranker=retrieval_profile.reranker,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
        context_blocks = [str(candidate.payload.get("chunk_text") or candidate.payload.get("title") or "") for candidate in selected]
        citations = [self._normalize_citation(index, candidate) for index, candidate in enumerate(selected, start=1)]
        await self._costs.record_usage(
            session=session,
            context=context,
            usage=usage_context,
            input_tokens=input_tokens,
            output_tokens=0,
            estimated_cost_usd=self._costs.estimate_cost(
                input_tokens=input_tokens,
                output_tokens=0,
                input_cost_per_1k=runtime.input_cost_per_1k,
                output_cost_per_1k=Decimal("0"),
            ),
        )
        return RetrievalResult(
            query=request.query,
            context_blocks=context_blocks,
            citations=citations,
            retrieval_profile_id=retrieval_profile.id,
            total_candidates=len(candidates),
            used_candidates=len(selected),
        )

    async def _resolve_retrieval_profile(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        spaces: list[KnowledgeSpace],
        request: RetrievalRequest,
    ) -> RetrievalProfile:
        profile_id = request.retrieval_profile_id or spaces[0].retrieval_profile_id
        statement = select(RetrievalProfile).where(RetrievalProfile.tenant_id == tenant_id)
        if profile_id is not None:
            statement = statement.where(RetrievalProfile.id == profile_id)
        else:
            statement = statement.where(RetrievalProfile.is_default.is_(True))
        profile = (await session.execute(statement)).scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid retrieval profile.")
        return profile

    async def _resolve_embedding_profile(self, session: AsyncSession, embedding_profile_id: UUID) -> EmbeddingProfile:
        profile = await session.scalar(select(EmbeddingProfile).where(EmbeddingProfile.id == embedding_profile_id))
        if profile is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid embedding profile.")
        return profile

    async def _hybrid_search(
        self,
        *,
        query: str,
        embedding_profile: EmbeddingProfile,
        retrieval_profile: RetrievalProfile,
        filter_obj: models.Filter,
        runtime,
    ) -> list[_Candidate]:
        query_vector = (
            await self._embeddings.embed_texts(
                model=runtime.runtime_model_name,
                texts=[query],
                dimensions=embedding_profile.dimensions,
                batch_size=1,
                provider_api_key=runtime.provider_api_key,
                provider_base_url=runtime.provider_base_url,
            )
        )[0]

        dense_results = await self._qdrant_search_with_retries(
            query_vector=query_vector,
            filter_obj=filter_obj,
            limit=retrieval_profile.top_k,
        )
        lexical_results = await self._lexical_search_with_retries(
            filter_obj=filter_obj,
            query=query,
            limit=retrieval_profile.top_k,
        )

        combined: dict[str, tuple[dict[str, object], float]] = {}
        rrf_scores: defaultdict[str, float] = defaultdict(float)
        for rank, point in enumerate(dense_results, start=1):
            payload = dict(point.payload or {})
            point_id = str(point.id)
            combined[point_id] = (payload, float(point.score))
            rrf_scores[point_id] += retrieval_profile.dense_weight * (1.0 / (60 + rank))

        for rank, candidate in enumerate(lexical_results, start=1):
            combined[candidate.point_id] = (candidate.payload, candidate.score)
            rrf_scores[candidate.point_id] += retrieval_profile.sparse_weight * (1.0 / (60 + rank))

        candidates = [
            _Candidate(point_id=point_id, payload=payload, score=rrf_scores[point_id])
            for point_id, (payload, _) in combined.items()
        ]
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates

    def _is_retryable_qdrant_error(self, exc: UnexpectedResponse) -> bool:
        return getattr(exc, "status_code", None) in {404, 500}

    async def _qdrant_search_with_retries(
        self,
        *,
        query_vector: list[float],
        filter_obj: models.Filter,
        limit: int,
    ):
        last_error: UnexpectedResponse | None = None
        for _ in range(10):
            try:
                return await asyncio.to_thread(
                    self._qdrant.search,
                    collection_name="aura_chunks",
                    query_vector=query_vector,
                    query_filter=filter_obj,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
            except UnexpectedResponse as exc:
                if not self._is_retryable_qdrant_error(exc):
                    raise
                last_error = exc
                await asyncio.sleep(0.2)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Qdrant search failed without an error")

    async def _lexical_search_with_retries(
        self,
        *,
        filter_obj: models.Filter,
        query: str,
        limit: int,
    ) -> list[_Candidate]:
        last_error: UnexpectedResponse | None = None
        for _ in range(10):
            try:
                return await asyncio.to_thread(self._lexical_search, filter_obj, query, limit)
            except UnexpectedResponse as exc:
                if not self._is_retryable_qdrant_error(exc):
                    raise
                last_error = exc
                await asyncio.sleep(0.2)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Qdrant scroll failed without an error")

    def _lexical_search(self, filter_obj: models.Filter, query: str, limit: int) -> list[_Candidate]:
        points, _ = self._qdrant.scroll(
            "aura_chunks",
            scroll_filter=filter_obj,
            with_payload=True,
            with_vectors=False,
            limit=max(limit * 10, 50),
        )
        query_terms = self._tokenize(query)
        candidates: list[_Candidate] = []
        for point in points:
            payload = dict(point.payload or {})
            haystack = " ".join(
                value for value in (str(payload.get("chunk_text") or ""), str(payload.get("title") or "")) if value
            )
            score = self._lexical_score(query_terms, haystack)
            if score <= 0:
                continue
            candidates.append(_Candidate(point_id=str(point.id), payload=payload, score=score))
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:limit]

    def _rerank_candidates(self, query: str, candidates: list[_Candidate], reranker: str) -> list[_Candidate]:
        if reranker == "none":
            return candidates
        query_terms = self._tokenize(query)
        reranked = [
            _Candidate(
                point_id=candidate.point_id,
                payload=candidate.payload,
                score=candidate.score + self._lexical_score(query_terms, str(candidate.payload.get("chunk_text") or "")),
            )
            for candidate in candidates
        ]
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked

    def _normalize_citation(self, index: int, candidate: _Candidate) -> Citation:
        payload = candidate.payload
        page_number = payload.get("page_number")
        section_title = payload.get("section_title")
        page_or_section = str(section_title or (f"page {page_number}" if page_number else "")) or None
        snippet = str(payload.get("chunk_text") or payload.get("title") or "")[:500]
        return Citation(
            citation_id=f"cit-{index}",
            document_id=UUID(str(payload["document_id"])),
            document_version_id=UUID(str(payload["document_version_id"])),
            chunk_id=UUID(str(payload["chunk_id"])),
            title=str(payload.get("title") or ""),
            source_system=str(payload.get("source_system") or ""),
            source_path=str(payload.get("source_path") or ""),
            source_url=str(payload["source_url"]) if payload.get("source_url") else None,
            page_or_section=page_or_section,
            score=float(candidate.score),
            snippet=snippet,
        )

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.findall(r"\w+", text.lower()) if token]

    def _lexical_score(self, query_terms: list[str], haystack: str) -> float:
        if not query_terms or not haystack:
            return 0.0
        haystack_terms = self._tokenize(haystack)
        if not haystack_terms:
            return 0.0
        overlap = sum(1 for token in query_terms if token in haystack_terms)
        return overlap / math.sqrt(len(haystack_terms))
