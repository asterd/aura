from __future__ import annotations

from dataclasses import dataclass
import json
import time

import httpx

from apps.api.config import settings
from aura.domain.contracts import RequestContext
from aura.utils.observability import record_litellm_call_latency, record_litellm_tokens_used


@dataclass(slots=True)
class LlmResult:
    content: str
    model_used: str
    tokens_used: int


class LiteLLMUnavailableError(RuntimeError):
    pass


class LlmService:
    def __init__(self) -> None:
        self._base_url = str(settings.litellm_base_url).rstrip("/")
        self._api_key = "sk-local-master-key"
        self._default_model = "gpt-4o-mini"

    async def generate(
        self,
        *,
        prompt: list[dict[str, str]],
        transformed_user_text: str,
        model_override: str | None,
        context: RequestContext,
    ) -> LlmResult:
        messages = self._materialize_messages(prompt, transformed_user_text)
        model = model_override or self._default_model
        record_litellm_tokens_used(
            model=model,
            tenant_id=str(context.tenant_id),
            direction="input",
            tokens=self.estimate_input_tokens(messages),
        )
        try:
            started = time.perf_counter()
            payload = await self._chat_completion(messages=messages, model=model, stream=False)
            choice = payload["choices"][0]["message"]["content"]
            content = choice.strip() if isinstance(choice, str) else ""
            usage = payload.get("usage") or {}
            result = LlmResult(
                content=content or "Non ho trovato contenuto sufficiente per rispondere.",
                model_used=str(payload.get("model") or model),
                tokens_used=int(usage.get("total_tokens") or max(1, len((content or "").split()))),
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            record_litellm_call_latency(model=result.model_used, tenant_id=str(context.tenant_id), latency_ms=latency_ms)
            record_litellm_tokens_used(
                model=result.model_used,
                tenant_id=str(context.tenant_id),
                direction="output",
                tokens=result.tokens_used,
            )
            return result
        except Exception as exc:
            raise LiteLLMUnavailableError(model) from exc

    async def stream_generate(
        self,
        *,
        prompt: list[dict[str, str]],
        transformed_user_text: str,
        model_override: str | None,
        context: RequestContext,
    ):
        messages = self._materialize_messages(prompt, transformed_user_text)
        model = model_override or self._default_model
        record_litellm_tokens_used(
            model=model,
            tenant_id=str(context.tenant_id),
            direction="input",
            tokens=self.estimate_input_tokens(messages),
        )
        try:
            started = time.perf_counter()
            total_tokens = 0
            async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": model, "messages": messages, "stream": True},
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            return
                        payload = json.loads(data)
                        delta = payload["choices"][0]["delta"].get("content")
                        if isinstance(delta, str) and delta:
                            total_tokens += max(1, len(delta.split()))
                            yield delta
            record_litellm_call_latency(model=model, tenant_id=str(context.tenant_id), latency_ms=(time.perf_counter() - started) * 1000.0)
            if total_tokens:
                record_litellm_tokens_used(
                    model=model,
                    tenant_id=str(context.tenant_id),
                    direction="output",
                    tokens=total_tokens,
                )
            return
        except Exception as exc:
            raise LiteLLMUnavailableError(model) from exc

    async def _chat_completion(self, *, messages: list[dict[str, str]], model: str, stream: bool) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": model, "messages": messages, "stream": stream},
            )
            response.raise_for_status()
            return response.json()

    def _materialize_messages(self, prompt: list[dict[str, str]], transformed_user_text: str) -> list[dict[str, str]]:
        messages = [dict(message) for message in prompt]
        for message in reversed(messages):
            if message.get("role") == "user":
                message["content"] = transformed_user_text
                break
        else:
            messages.append({"role": "user", "content": transformed_user_text})
        return messages

    def estimate_input_tokens(self, messages: list[dict[str, str]]) -> int:
        return max(1, sum(len(str(message.get("content") or "").split()) for message in messages))
