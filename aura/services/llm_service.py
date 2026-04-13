from __future__ import annotations

from dataclasses import dataclass
import json

import httpx

from apps.api.config import settings
from aura.domain.contracts import RequestContext


@dataclass(slots=True)
class LlmResult:
    content: str
    model_used: str
    tokens_used: int


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
        try:
            payload = await self._chat_completion(messages=messages, model=model, stream=False)
            choice = payload["choices"][0]["message"]["content"]
            content = choice.strip() if isinstance(choice, str) else ""
            usage = payload.get("usage") or {}
            return LlmResult(
                content=content or "Non ho trovato contenuto sufficiente per rispondere.",
                model_used=str(payload.get("model") or model),
                tokens_used=int(usage.get("total_tokens") or max(1, len((content or "").split()))),
            )
        except Exception:
            content = transformed_user_text.strip() or "Non ho trovato contenuto sufficiente per rispondere."
            return LlmResult(
                content=content,
                model_used=f"{model}:fallback",
                tokens_used=max(1, len(content.split())),
            )

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
        try:
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
                            yield delta
            return
        except Exception:
            result = await self.generate(
                prompt=prompt,
                transformed_user_text=transformed_user_text,
                model_override=model_override,
                context=context,
            )
            for token in result.content.split():
                yield f"{token} "

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
