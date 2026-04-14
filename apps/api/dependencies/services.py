from __future__ import annotations

from fastapi import Depends

from aura.adapters.mcp import HttpSseMcpBridgeAdapter
from aura.adapters.sandbox.factory import get_default as get_default_sandbox_provider
from aura.services.agent_chat_service import AgentChatService
from aura.services.agent_service import AgentService
from aura.services.chat import ChatService
from aura.services.conversation_service import ConversationService
from aura.services.cost_management_service import CostManagementService
from aura.services.datasource_service import DatasourceService
from aura.services.event_dispatcher_service import EventDispatcherService
from aura.services.llm_provider_service import LlmProviderService
from aura.services.litellm_admin_service import LiteLLMAdminService
from aura.services.llm_service import LlmService
from aura.services.mcp_server_service import McpServerService
from aura.services.registry_service import RegistryService
from aura.services.retrieval import RetrievalService
from aura.services.skill_service import SkillService
from aura.services.space_service import SpaceService
from aura.services.trigger_scheduler_service import TriggerSchedulerService


def get_retrieval_service() -> RetrievalService:
    return RetrievalService()


def get_space_service() -> SpaceService:
    return SpaceService()


def get_llm_provider_service() -> LlmProviderService:
    return LlmProviderService()


def get_cost_management_service() -> CostManagementService:
    return CostManagementService()


def get_litellm_admin_service(
    llm_provider_service: LlmProviderService = Depends(get_llm_provider_service),
    cost_management_service: CostManagementService = Depends(get_cost_management_service),
) -> LiteLLMAdminService:
    return LiteLLMAdminService(
        llm_provider_service=llm_provider_service,
        cost_management_service=cost_management_service,
    )


def get_llm_service(
    llm_provider_service: LlmProviderService = Depends(get_llm_provider_service),
    cost_management_service: CostManagementService = Depends(get_cost_management_service),
) -> LlmService:
    return LlmService(
        llm_provider_service=llm_provider_service,
        cost_management_service=cost_management_service,
    )


def get_chat_service(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    llm_service: LlmService = Depends(get_llm_service),
) -> ChatService:
    return ChatService(retrieval_service=retrieval_service, llm_service=llm_service)


def get_conversation_service() -> ConversationService:
    return ConversationService()


def get_registry_service() -> RegistryService:
    return RegistryService()


def get_skill_service() -> SkillService:
    return SkillService(
        sandbox_provider=get_default_sandbox_provider(),
        mcp_adapter_factory=lambda url: HttpSseMcpBridgeAdapter(server_url=url),
    )


def get_agent_service(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    registry_service: RegistryService = Depends(get_registry_service),
    skill_service: SkillService = Depends(get_skill_service),
) -> AgentService:
    return AgentService(
        retrieval_service=retrieval_service,
        registry_service=registry_service,
        skill_service=skill_service,
    )


def get_agent_chat_service(
    agent_service: AgentService = Depends(get_agent_service),
    chat_service: ChatService = Depends(get_chat_service),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> AgentChatService:
    return AgentChatService(agent_service=agent_service, chat_service=chat_service, retrieval_service=retrieval_service)


def get_trigger_scheduler_service(
    agent_service: AgentService = Depends(get_agent_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> TriggerSchedulerService:
    return TriggerSchedulerService(agent_service=agent_service, registry_service=registry_service)


def get_event_dispatcher_service(
    agent_service: AgentService = Depends(get_agent_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> EventDispatcherService:
    return EventDispatcherService(agent_service=agent_service, registry_service=registry_service)


def get_datasource_service(
    space_service: SpaceService = Depends(get_space_service),
) -> DatasourceService:
    return DatasourceService(space_service=space_service)


def get_mcp_server_service(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    chat_service: ChatService = Depends(get_chat_service),
    agent_service: AgentService = Depends(get_agent_service),
    space_service: SpaceService = Depends(get_space_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> McpServerService:
    return McpServerService(
        retrieval_service=retrieval_service,
        chat_service=chat_service,
        agent_service=agent_service,
        space_service=space_service,
        registry_service=registry_service,
    )
