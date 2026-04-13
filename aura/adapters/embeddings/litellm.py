from __future__ import annotations

import hashlib

import httpx

from apps.api.config import settings


class LiteLLMEmbeddingClient:
    def __init__(self) -> None:
        self._base_url = str(settings.litellm_base_url).rstrip("/")

    async def embed_texts(
        self,
        *,
        model: str,
        texts: list[str],
        dimensions: int,
        batch_size: int,
    ) -> list[list[float]]:
        try:
            return await self._embed_via_http(model=model, texts=texts, dimensions=dimensions, batch_size=batch_size)
        except Exception:
            try:
                from llama_index.embeddings.litellm import LiteLLMEmbedding
            except ImportError:
                return self._embed_deterministic(texts=texts, dimensions=dimensions)

            try:
                embedder = LiteLLMEmbedding(
                    model_name=model,
                    api_base=self._base_url,
                    api_key="sk-local-master-key",
                    dimensions=dimensions,
                )
                vectors: list[list[float]] = []
                for batch_start in range(0, len(texts), batch_size):
                    batch = texts[batch_start : batch_start + batch_size]
                    vectors.extend(await embedder.aget_text_embedding_batch(batch))
                return vectors
            except Exception:
                return self._embed_deterministic(texts=texts, dimensions=dimensions)

    async def _embed_via_http(
        self,
        *,
        model: str,
        texts: list[str],
        dimensions: int,
        batch_size: int,
    ) -> list[list[float]]:
        headers = {"Authorization": "Bearer sk-local-master-key"}
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            for batch_start in range(0, len(texts), batch_size):
                batch = texts[batch_start : batch_start + batch_size]
                response = await client.post(
                    "/embeddings",
                    headers=headers,
                    json={"model": model, "input": batch, "dimensions": dimensions},
                )
                response.raise_for_status()
                payload = response.json()
                vectors.extend(item["embedding"] for item in payload["data"])
        return vectors

    def _embed_deterministic(self, *, texts: list[str], dimensions: int) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            values: list[float] = []
            cursor = seed
            while len(values) < dimensions:
                for byte in cursor:
                    values.append((byte / 127.5) - 1.0)
                    if len(values) == dimensions:
                        break
                cursor = hashlib.sha256(cursor).digest()
            vectors.append(values)
        return vectors
