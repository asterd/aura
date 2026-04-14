from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import time
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.domain.contracts import LlmTaskType, RequestContext
from aura.services.cost_management_service import CostManagementService, UsageContext
from aura.services.llm_provider_service import LlmProviderService
from aura.utils.observability import record_litellm_call_latency, record_litellm_tokens_used


@dataclass(slots=True)
class LlmResult:
    content: str
    model_used: str
    tokens_used: int


class LiteLLMUnavailableError(RuntimeError):
    pass


class LlmService:
    def __init__(
        self,
        *,
        llm_provider_service: LlmProviderService | None = None,
        cost_management_service: CostManagementService | None = None,
    ) -> None:
        self._base_url = str(settings.litellm_base_url).rstrip("/")
        self._proxy_api_key = settings.litellm_master_key.get_secret_value()
        self._providers = llm_provider_service or LlmProviderService()
        self._costs = cost_management_service or CostManagementService()

    async def generate(
        self,
        *,
        session: AsyncSession,
        prompt: list[dict[str, str]],
        transformed_user_text: str,
        model_override: str | None,
        context: RequestContext,
        space_ids: list[UUID] | None = None,
        conversation_id: UUID | None = None,
    ) -> LlmResult:
        messages = self._materialize_messages(prompt, transformed_user_text)
        runtime = await self._providers.resolve_model(
            session=session,
            tenant_id=context.tenant_id,
            requested_model=model_override,
            task_type=LlmTaskType.chat,
        )
        input_tokens = self.estimate_input_tokens(messages)
        usage_context = UsageContext(
            provider_id=runtime.provider_id,
            provider_key=runtime.provider_key,
            model_name=runtime.runtime_model_name,
            task_type=LlmTaskType.chat,
            space_id=space_ids[0] if space_ids else None,
            conversation_id=conversation_id,
            credential_id=runtime.credential_id,
        )
        await self._costs.check_budget(
            session=session,
            context=context,
            usage=usage_context,
            projected_cost_usd=self._costs.estimate_cost(
                input_tokens=input_tokens,
                output_tokens=0,
                input_cost_per_1k=runtime.input_cost_per_1k,
                output_cost_per_1k=Decimal("0"),
            ),
        )
        record_litellm_tokens_used(
            model=runtime.runtime_model_name,
            tenant_id=str(context.tenant_id),
            direction="input",
            tokens=input_tokens,
        )
        try:
            started = time.perf_counter()
            payload = await self._chat_completion(
                messages=messages,
                runtime_model=runtime.runtime_model_name,
                provider_api_key=runtime.provider_api_key,
                provider_base_url=runtime.provider_base_url,
                stream=False,
            )
            content = self._extract_content(payload)
            usage = payload.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or input_tokens)
            completion_tokens = int(
                usage.get("completion_tokens") or max(1, len((content or "Non ho trovato contenuto sufficiente per rispondere.").split()))
            )
            result = LlmResult(
                content=content or "Non ho trovato contenuto sufficiente per rispondere.",
                model_used=str(payload.get("model") or runtime.runtime_model_name),
                tokens_used=prompt_tokens + completion_tokens,
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            record_litellm_call_latency(model=result.model_used, tenant_id=str(context.tenant_id), latency_ms=latency_ms)
            record_litellm_tokens_used(
                model=result.model_used,
                tenant_id=str(context.tenant_id),
                direction="output",
                tokens=completion_tokens,
            )
            await self._costs.record_usage(
                session=session,
                context=context,
                usage=usage_context,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                estimated_cost_usd=self._costs.estimate_cost(
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    input_cost_per_1k=runtime.input_cost_per_1k,
                    output_cost_per_1k=runtime.output_cost_per_1k,
                ),
            )
            return result
        except Exception as exc:
            if runtime.model_config_id is None:
                content = self._build_legacy_fallback_content(transformed_user_text)
                completion_tokens = max(1, len(content.split()))
                await self._costs.record_usage(
                    session=session,
                    context=context,
                    usage=usage_context,
                    input_tokens=input_tokens,
                    output_tokens=completion_tokens,
                    estimated_cost_usd=Decimal("0"),
                )
                return LlmResult(
                    content=content,
                    model_used=runtime.runtime_model_name,
                    tokens_used=input_tokens + completion_tokens,
                )
            raise LiteLLMUnavailableError(runtime.runtime_model_name) from exc

    async def stream_generate(
        self,
        *,
        session: AsyncSession,
        prompt: list[dict[str, str]],
        transformed_user_text: str,
        model_override: str | None,
        context: RequestContext,
        space_ids: list[UUID] | None = None,
        conversation_id: UUID | None = None,
    ):
        messages = self._materialize_messages(prompt, transformed_user_text)
        runtime = await self._providers.resolve_model(
            session=session,
            tenant_id=context.tenant_id,
            requested_model=model_override,
            task_type=LlmTaskType.chat,
        )
        input_tokens = self.estimate_input_tokens(messages)
        usage_context = UsageContext(
            provider_id=runtime.provider_id,
            provider_key=runtime.provider_key,
            model_name=runtime.runtime_model_name,
            task_type=LlmTaskType.chat,
            space_id=space_ids[0] if space_ids else None,
            conversation_id=conversation_id,
            credential_id=runtime.credential_id,
        )
        await self._costs.check_budget(
            session=session,
            context=context,
            usage=usage_context,
            projected_cost_usd=self._costs.estimate_cost(
                input_tokens=input_tokens,
                output_tokens=0,
                input_cost_per_1k=runtime.input_cost_per_1k,
                output_cost_per_1k=Decimal("0"),
            ),
        )
        record_litellm_tokens_used(
            model=runtime.runtime_model_name,
            tenant_id=str(context.tenant_id),
            direction="input",
            tokens=input_tokens,
        )
        try:
            started = time.perf_counter()
            completion_tokens = 0
            async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {self._proxy_api_key}"},
                    json=self._build_payload(
                        runtime_model=runtime.runtime_model_name,
                        messages=messages,
                        provider_api_key=runtime.provider_api_key,
                        provider_base_url=runtime.provider_base_url,
                        stream=True,
                    ),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        payload = json.loads(data)
                        delta = payload["choices"][0]["delta"].get("content")
                        if isinstance(delta, str) and delta:
                            completion_tokens += max(1, len(delta.split()))
                            yield delta
            record_litellm_call_latency(
                model=runtime.runtime_model_name,
                tenant_id=str(context.tenant_id),
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            if completion_tokens:
                record_litellm_tokens_used(
                    model=runtime.runtime_model_name,
                    tenant_id=str(context.tenant_id),
                    direction="output",
                    tokens=completion_tokens,
                )
            await self._costs.record_usage(
                session=session,
                context=context,
                usage=usage_context,
                input_tokens=input_tokens,
                output_tokens=completion_tokens,
                estimated_cost_usd=self._costs.estimate_cost(
                    input_tokens=input_tokens,
                    output_tokens=completion_tokens,
                    input_cost_per_1k=runtime.input_cost_per_1k,
                    output_cost_per_1k=runtime.output_cost_per_1k,
                ),
            )
            return
        except Exception as exc:
            if runtime.model_config_id is None:
                content = self._build_legacy_fallback_content(transformed_user_text)
                completion_tokens = max(1, len(content.split()))
                await self._costs.record_usage(
                    session=session,
                    context=context,
                    usage=usage_context,
                    input_tokens=input_tokens,
                    output_tokens=completion_tokens,
                    estimated_cost_usd=Decimal("0"),
                )
                yield content
                return
            raise LiteLLMUnavailableError(runtime.runtime_model_name) from exc

    async def _chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        runtime_model: str,
        provider_api_key: str,
        provider_base_url: str | None,
        stream: bool,
    ) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._proxy_api_key}"},
                json=self._build_payload(
                    runtime_model=runtime_model,
                    messages=messages,
                    provider_api_key=provider_api_key,
                    provider_base_url=provider_base_url,
                    stream=stream,
                ),
            )
            response.raise_for_status()
            return response.json()

    def _build_payload(
        self,
        *,
        runtime_model: str,
        messages: list[dict[str, str]],
        provider_api_key: str,
        provider_base_url: str | None,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": runtime_model,
            "messages": messages,
            "stream": stream,
        }
        if provider_api_key:
            payload["api_key"] = provider_api_key
        if provider_base_url:
            payload["api_base"] = provider_base_url
        return payload

    def _extract_content(self, payload: dict) -> str:
        choice = payload["choices"][0]["message"]["content"]
        if isinstance(choice, str):
            return choice.strip()
        if isinstance(choice, list):
            return "".join(part.get("text", "") for part in choice if isinstance(part, dict)).strip()
        return ""

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

    def _build_legacy_fallback_content(self, transformed_user_text: str) -> str:
        normalized = transformed_user_text.strip() or "Richiesta ricevuta."
        return f"Risposta provvisoria: {normalized}"
