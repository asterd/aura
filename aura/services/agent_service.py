from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from aura.adapters.db.models import AgentRun
from aura.adapters.runtime.loader import RuntimeLoader, RuntimeLoaderError
from aura.domain.contracts import AgentDeps, AgentRunRequest, AgentRunResult, RequestContext, RetrievalRequest
from aura.services.audit_service import AuditService
from aura.services.authz_service import AuthzService
from aura.services.pii_service import PiiService
from aura.services.policy_service import PolicyService
from aura.services.prompt_service import PromptService
from aura.services.registry_service import RegistryService, ResolvedAgentVersion
from aura.services.retrieval import RetrievalService
from aura.adapters.s3.client import S3Client


logger = logging.getLogger("aura")


@dataclass(slots=True)
class _KnowledgeSearchResult:
    context_text: str


class _AgentKnowledgeService:
    def __init__(self, retrieval_service: RetrievalService, session: AsyncSession, context: RequestContext) -> None:
        self._retrieval = retrieval_service
        self._session = session
        self._context = context

    async def search(self, *, query: str, space_id: UUID, identity) -> _KnowledgeSearchResult:
        del identity
        result = await self._retrieval.retrieve(
            session=self._session,
            request=RetrievalRequest(query=query, space_ids=[space_id]),
            context=self._context,
        )
        return _KnowledgeSearchResult(context_text="\n\n".join(result.context_blocks))


class _RunArtifactWriter:
    def __init__(self, s3_client: S3Client | None = None) -> None:
        self._s3 = s3_client or S3Client()
        self._artifact_refs: list[str] = []

    @property
    def artifact_refs(self) -> list[str]:
        return list(self._artifact_refs)

    async def write(self, *, name: str, content: bytes, content_type: str, identity) -> str:
        key = f"agent-artifacts/{identity.tenant_id}/{identity.user_id}/{datetime.now(UTC).timestamp()}-{name}"
        ref = await self._s3.upload_file(settings.s3_bucket_name, key, content, content_type)
        self._artifact_refs.append(ref)
        return ref


class AgentService:
    def __init__(
        self,
        *,
        registry_service: RegistryService | None = None,
        authz_service: AuthzService | None = None,
        policy_service: PolicyService | None = None,
        prompt_service: PromptService | None = None,
        pii_service: PiiService | None = None,
        runtime_loader: RuntimeLoader | None = None,
        retrieval_service: RetrievalService | None = None,
        audit_service: AuditService | None = None,
        s3_client: S3Client | None = None,
    ) -> None:
        self._registry = registry_service or RegistryService()
        self._authz = authz_service or AuthzService()
        self._policies = policy_service or PolicyService()
        self._prompt = prompt_service or PromptService()
        self._pii = pii_service or PiiService()
        self._loader = runtime_loader or RuntimeLoader()
        self._retrieval = retrieval_service or RetrievalService()
        self._audit = audit_service or AuditService()
        self._s3 = s3_client or S3Client()

    async def run_agent(
        self,
        *,
        session: AsyncSession,
        request: AgentRunRequest,
        context: RequestContext,
    ) -> AgentRunResult:
        version = await self._registry.resolve_agent_version(
            session=session,
            agent_name=request.agent_name,
            requested_version=request.agent_version,
            tenant_id=context.tenant_id,
        )
        if version.status != "published":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only published agents are executable.")

        await self._authz.ensure_can_run_agent(session=session, identity=context.identity, agent_version=version)

        model_policy = await self._policies.resolve_model_policy(session, version, context)
        pii_policy = await self._policies.resolve_pii_policy(session, version, context)
        system_prompt = await self._prompt.resolve_agent_prompt(session=session, version=version, context=context)

        artifact_writer = _RunArtifactWriter(self._s3)
        deps = AgentDeps(
            identity=context.identity,
            model_policy=model_policy,
            pii_policy=pii_policy,
            allowed_spaces=version.allowed_space_ids,
            allowed_tools=version.allowed_tools,
            litellm_base_url=str(settings.litellm_base_url),
            litellm_virtual_key=await self._authz.resolve_virtual_key(session, version, context),
            knowledge_service=_AgentKnowledgeService(self._retrieval, session, context),
            artifact_writer=artifact_writer,
            resolve_system_prompt=lambda _: system_prompt,
        )

        artifact_ref = await self._registry.get_runtime_artifact_ref(session, version)
        build_fn = await self._loader.load_build_fn(artifact_ref, version.entrypoint, version.artifact_sha256)
        temp_dir = getattr(build_fn, "__aura_temp_dir__", None)
        try:
            transformed_input = await self._pii.transform_agent_input_if_needed(
                session=session,
                context=context,
                input_obj=request.input,
                policy=pii_policy,
            )
            agent = build_fn(deps)
            self._enforce_allowed_tools(agent, allowed_tools=version.allowed_tools)
            raw_result = await agent.run(transformed_input, deps=deps)
            raw_output = getattr(raw_result, "output", raw_result)
            transformed_output = await self._pii.transform_agent_output_if_needed(
                session=session,
                context=context,
                output_obj=raw_output if isinstance(raw_output, dict) else {"result": raw_output},
                policy=pii_policy,
            )
            persisted = await self._create_run(
                session=session,
                context=context,
                version=version,
                request=request,
                status="succeeded",
                output=transformed_output,
                error_message=None,
                artifact_refs=artifact_writer.artifact_refs,
            )
            await self._audit.emit_agent_run(session=session, context=context, run_id=persisted.id)
            output_text = transformed_output if isinstance(transformed_output, str) else transformed_output.get("result")
            output_data = transformed_output if isinstance(transformed_output, dict) else None
            return AgentRunResult(
                run_id=persisted.id,
                agent_name=version.name,
                agent_version=version.version,
                status="succeeded",
                output_data=output_data,
                output_text=output_text if isinstance(output_text, str) else None,
                trace_id=context.trace_id,
                artifacts=artifact_writer.artifact_refs,
            )
        except RuntimeLoaderError:
            raise
        except Exception as exc:
            persisted = await self._create_run(
                session=session,
                context=context,
                version=version,
                request=request,
                status="failed",
                output=None,
                error_message=f"{type(exc).__name__}: {exc}",
                artifact_refs=artifact_writer.artifact_refs,
            )
            await self._audit.emit_agent_run(session=session, context=context, run_id=persisted.id)
            logger.exception("agent_run_failed agent=%s version=%s trace_id=%s", version.name, version.version, context.trace_id)
            return AgentRunResult(
                run_id=persisted.id,
                agent_name=version.name,
                agent_version=version.version,
                status="failed",
                trace_id=context.trace_id,
                artifacts=artifact_writer.artifact_refs,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        finally:
            await self._loader.cleanup_temp_dir(temp_dir)

    async def _create_run(
        self,
        *,
        session: AsyncSession,
        context: RequestContext,
        version: ResolvedAgentVersion,
        request: AgentRunRequest,
        status: str,
        output: dict[str, Any] | None,
        error_message: str | None,
        artifact_refs: list[str],
    ) -> AgentRun:
        output_text = None
        output_data = output
        if isinstance(output, dict) and isinstance(output.get("result"), str):
            output_text = output["result"]
        run = AgentRun(
            id=request.run_id,
            tenant_id=context.tenant_id,
            agent_version_id=version.id,
            user_id=context.identity.user_id,
            conversation_id=request.conversation_id,
            status=status,
            output_data=output_data,
            output_text=output_text,
            error_message=error_message,
            trace_id=context.trace_id,
            artifact_refs=artifact_refs,
            completed_at=context.now_utc,
        )
        session.add(run)
        await session.flush()
        return run

    def _enforce_allowed_tools(self, agent: Any, *, allowed_tools: list[str]) -> None:
        tool_map = getattr(agent, "_function_tools", None)
        if not isinstance(tool_map, dict):
            return
        unauthorized = [name for name in list(tool_map.keys()) if name not in allowed_tools]
        for name in unauthorized:
            tool_map.pop(name, None)
