from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID
from uuid import uuid4

from aura.domain.contracts import (
    AgentChatInput,
    AgentInvocation,
    AgentRunRequest,
    AgentRunResult,
    ChatRequest,
    ChatStreamEvent,
    ChatStreamEventAgentDone,
    ChatStreamEventAgentRunning,
    RetrievalResult,
)
from aura.services.agent_service import AgentService
from aura.services.chat import ChatService
from aura.services.registry_service import RegistryService
from aura.services.retrieval import RetrievalService


logger = logging.getLogger("aura")


@dataclass(slots=True)
class _ResolvedInvocation:
    invocation: AgentInvocation
    invocation_mode: str


class AgentChatService:
    def __init__(
        self,
        *,
        agent_service: AgentService | None = None,
        chat_service: ChatService | None = None,
        retrieval_service: RetrievalService | None = None,
        registry_service: RegistryService | None = None,
    ) -> None:
        self._agents = agent_service or AgentService()
        self._chat = chat_service or ChatService(retrieval_service=retrieval_service)
        self._retrieval = retrieval_service or RetrievalService()
        self._registry = registry_service or RegistryService()

    async def respond(self, *, session, ctx, request: ChatRequest, history: list[dict]):
        invocations = await self._resolve_invocations(session=session, tenant_id=ctx.tenant_id, request=request)
        retrieval_task = asyncio.create_task(
            self._retrieval.retrieve(
                session=session,
                request=self._build_retrieval_request(request),
                context=ctx,
            )
        )
        agent_tasks = [
            asyncio.create_task(
                self._run_agent_for_chat(
                    session,
                    ctx,
                    resolved.invocation,
                    request.message,
                    history,
                    request.conversation_id,
                    request.space_ids,
                    None,
                )
            )
            for resolved in invocations
        ]
        retrieval_result, *agent_results = await asyncio.gather(retrieval_task, *agent_tasks, return_exceptions=True)
        retrieval_result = self._normalize_retrieval_result(request, retrieval_result)
        enhanced = self._build_enhanced_context(retrieval_result, agent_results, invocations)
        successful_runs = self._collect_successful_runs(invocations, agent_results)
        return await self._chat.respond_with_context(
            session=session,
            context=ctx,
            request=request,
            retrieval_result=enhanced,
            agent_runs=successful_runs,
        )

    async def respond_stream(self, *, session, ctx, request: ChatRequest, history: list[dict]) -> AsyncGenerator[ChatStreamEvent, None]:
        invocations = await self._resolve_invocations(session=session, tenant_id=ctx.tenant_id, request=request)
        run_ids = {self._invocation_key(resolved.invocation): uuid4() for resolved in invocations}
        for resolved in invocations:
            yield ChatStreamEventAgentRunning(
                type="agent_running",
                agent_name=resolved.invocation.agent_name,
                run_id=run_ids[self._invocation_key(resolved.invocation)],
            )
        retrieval_task = asyncio.create_task(
            self._retrieval.retrieve(
                session=session,
                request=self._build_retrieval_request(request),
                context=ctx,
            )
        )
        agent_tasks = [
            asyncio.create_task(
                self._run_agent_for_chat(
                    session,
                    ctx,
                    resolved.invocation,
                    request.message,
                    history,
                    request.conversation_id,
                    request.space_ids,
                    run_ids[self._invocation_key(resolved.invocation)],
                )
            )
            for resolved in invocations
        ]
        retrieval_result, *agent_results = await asyncio.gather(retrieval_task, *agent_tasks, return_exceptions=True)
        retrieval_result = self._normalize_retrieval_result(request, retrieval_result)
        for resolved, result in zip(invocations, agent_results, strict=True):
            invocation = resolved.invocation
            if isinstance(result, AgentRunResult):
                yield ChatStreamEventAgentDone(
                    type="agent_done",
                    agent_name=invocation.agent_name,
                    run_id=result.run_id,
                    status=result.status,
                    artifacts=result.artifacts,
                )
            else:
                yield ChatStreamEventAgentDone(
                    type="agent_done",
                    agent_name=invocation.agent_name,
                    run_id=run_ids[self._invocation_key(invocation)],
                    status="failed",
                    artifacts=[],
                )
        enhanced = self._build_enhanced_context(retrieval_result, agent_results, invocations)
        successful_runs = self._collect_successful_runs(invocations, agent_results)
        async for event in self._chat.respond_stream_with_context(
            session=session,
            context=ctx,
            request=request,
            retrieval_result=enhanced,
            agent_runs=successful_runs,
        ):
            yield event

    async def _run_agent_for_chat(
        self,
        session,
        ctx,
        invocation: AgentInvocation,
        user_message: str,
        history: list[dict],
        conversation_id,
        space_ids,
        run_id,
    ) -> AgentRunResult:
        input_data = invocation.input_override or AgentChatInput(
            user_message=user_message,
            recent_messages=history[-10:],
            space_ids=space_ids,
        ).model_dump(mode="json")
        return await self._agents.run_agent(
            session=session,
            context=ctx,
            request=AgentRunRequest(
                run_id=run_id,
                agent_name=invocation.agent_name,
                agent_version=invocation.agent_version,
                input=input_data,
                conversation_id=conversation_id,
            ),
        )

    async def _resolve_invocations(self, *, session, tenant_id, request: ChatRequest) -> list[_ResolvedInvocation]:
        merged: dict[tuple[str, str | None], _ResolvedInvocation] = {}
        for name in self._parse_mentions(request.message):
            invocation = AgentInvocation(agent_name=name)
            merged[self._invocation_key(invocation)] = _ResolvedInvocation(invocation=invocation, invocation_mode="mention")
        for invocation in request.invoked_agents:
            merged[self._invocation_key(invocation)] = _ResolvedInvocation(invocation=invocation, invocation_mode="explicit")
        if request.active_agent_ids:
            versions = await self._registry.list_versions(session, tenant_id)
            published_by_id = {version.id: version for version in versions if version.status == "published"}
            for agent_id in request.active_agent_ids:
                version = published_by_id.get(agent_id)
                if version is None:
                    continue
                invocation = AgentInvocation(agent_name=version.name, agent_version=version.version)
                merged[self._invocation_key(invocation)] = _ResolvedInvocation(invocation=invocation, invocation_mode="explicit")
        return list(merged.values())[:5]

    def _parse_mentions(self, message: str) -> list[str]:
        return re.findall(r"@([a-zA-Z0-9_-]+)", message)

    def _build_retrieval_request(self, request: ChatRequest):
        from aura.domain.contracts import RetrievalRequest

        return RetrievalRequest(
            query=request.message,
            space_ids=request.space_ids,
            conversation_id=request.conversation_id,
            retrieval_profile_id=request.retrieval_profile_id,
        )

    def _build_enhanced_context(
        self,
        retrieval_result: RetrievalResult,
        agent_results: list[AgentRunResult | Exception],
        invocations: list[_ResolvedInvocation],
    ) -> RetrievalResult:
        agent_blocks: list[str] = []
        for resolved, result in zip(invocations, agent_results, strict=True):
            invocation = resolved.invocation
            if isinstance(result, AgentRunResult):
                if result.status == "failed":
                    agent_blocks.append(f"[AGENT: {invocation.agent_name} — UNAVAILABLE: {result.error_message}]")
                else:
                    output_text = result.output_text or (result.output_data or {}).get("result", "")
                    agent_blocks.append(f"[AGENT: {invocation.agent_name} v{result.agent_version}]\n{output_text}\n---")
            else:
                logger.warning("agent_chat_run_failed agent=%s error=%s", invocation.agent_name, result)
                agent_blocks.append(f"[AGENT: {invocation.agent_name} — UNAVAILABLE: {result}]")

        return retrieval_result.model_copy(update={"context_blocks": [*agent_blocks, *retrieval_result.context_blocks]})

    def _normalize_retrieval_result(self, request: ChatRequest, retrieval_result) -> RetrievalResult:
        if isinstance(retrieval_result, RetrievalResult):
            return retrieval_result
        logger.warning("agent_chat_retrieval_failed error=%s", retrieval_result)
        return RetrievalResult(
            query=request.message,
            context_blocks=[],
            citations=[],
            retrieval_profile_id=request.retrieval_profile_id or UUID(int=0),
            total_candidates=0,
            used_candidates=0,
        )

    def _collect_successful_runs(
        self,
        invocations: list[_ResolvedInvocation],
        agent_results: list[AgentRunResult | Exception],
    ) -> list[dict[str, str | AgentRunResult]]:
        collected: list[dict[str, str | AgentRunResult]] = []
        for resolved, result in zip(invocations, agent_results, strict=True):
            if isinstance(result, AgentRunResult):
                collected.append({"result": result, "invocation_mode": resolved.invocation_mode})
        return collected

    def _invocation_key(self, invocation: AgentInvocation) -> tuple[str, str | None]:
        return invocation.agent_name, invocation.agent_version
