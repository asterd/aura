from __future__ import annotations

import logging
from pathlib import Path

import httpx

from apps.api.config import settings

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - optional dependency
    Langfuse = None


logger = logging.getLogger("aura")


class LangfuseUnavailableError(RuntimeError):
    pass


class LangfuseClient:
    def __init__(self) -> None:
        self._fallback_dir = Path(__file__).resolve().parents[3] / "registries" / "prompts" / "defaults"
        self._host = str(settings.langfuse_base_url).rstrip("/")
        self._secret_key = settings.langfuse_secret_key.get_secret_value()
        self._public_key = getattr(settings, "langfuse_public_key", None)
        self._client = self._build_client()

    def _build_client(self):
        if Langfuse is None:
            return None
        kwargs = {"host": self._host, "secret_key": self._secret_key}
        if self._public_key is not None:
            kwargs["public_key"] = self._public_key
        try:
            return Langfuse(**kwargs)
        except Exception:
            logger.warning("langfuse_client_init_failed", exc_info=True)
            return None

    async def get_prompt(self, prompt_id: str) -> str:
        try:
            prompt = await self._get_prompt_from_langfuse(prompt_id)
        except Exception as exc:
            raise LangfuseUnavailableError(prompt_id) from exc
        if not prompt:
            raise LangfuseUnavailableError(prompt_id)
        return prompt

    def load_fallback_prompt(self, prompt_id: str) -> str | None:
        fallback_path = self._fallback_dir / f"{prompt_id}.txt"
        if fallback_path.exists():
            return fallback_path.read_text(encoding="utf-8").strip()
        return None

    async def _get_prompt_from_langfuse(self, prompt_id: str) -> str | None:
        if self._client is not None:
            getter = getattr(self._client, "get_prompt", None)
            if callable(getter):
                result = getter(prompt_id)
                if hasattr(result, "__await__"):
                    result = await result
                prompt_text = _extract_prompt_text(result)
                if prompt_text:
                    return prompt_text

        headers = {"Authorization": f"Bearer {self._secret_key}"}
        async with httpx.AsyncClient(base_url=self._host, timeout=5.0) as client:
            response = await client.get(f"/api/public/prompts/{prompt_id}", headers=headers)
            response.raise_for_status()
        return _extract_prompt_text(response.json())


def _extract_prompt_text(payload) -> str | None:
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("prompt", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for attr in ("prompt", "text"):
        value = getattr(payload, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
