from __future__ import annotations

from apps.api.config import settings
from aura.adapters.mcp import HttpSseMcpBridgeAdapter
from aura.adapters.sandbox.docker import DockerSandboxProvider
from aura.adapters.sandbox.k8s import K8sJobSandboxProvider
from aura.services.agent_chat_service import AgentChatService
from aura.services.agent_service import AgentService
from aura.services.api_key_service import ApiKeyService
from aura.services.chat import ChatService
from aura.services.conversation_service import ConversationService
from aura.services.cost_management_service import CostManagementService
from aura.services.datasource_service import DatasourceService
from aura.services.event_dispatcher_service import EventDispatcherService
from aura.services.litellm_admin_service import LiteLLMAdminService
from aura.services.llm_provider_service import LlmProviderService
from aura.services.llm_service import LlmService
from aura.services.mcp_server_service import McpServerService
from aura.services.policy_service import PolicyService
from aura.services.registry_service import RegistryService
from aura.services.retrieval import RetrievalService
from aura.services.skill_service import SkillService
from aura.services.space_service import SpaceService
from aura.services.trigger_scheduler_service import TriggerSchedulerService


def _make_sandbox_provider():
    if settings.sandbox_provider == "docker":
        return DockerSandboxProvider()
    if settings.sandbox_provider == "k8s":
        return K8sJobSandboxProvider()
    raise ValueError(f"Unknown sandbox provider: {settings.sandbox_provider}")


sandbox_provider = _make_sandbox_provider()
api_key_service = ApiKeyService()
retrieval_service = RetrievalService()
policy_service = PolicyService()
space_service = SpaceService()
llm_provider_service = LlmProviderService()
cost_management_service = CostManagementService()
conversation_service = ConversationService()
registry_service = RegistryService()
skill_service = SkillService(
    sandbox_provider=sandbox_provider,
    mcp_adapter_factory=lambda url: HttpSseMcpBridgeAdapter(server_url=url),
)
litellm_admin_service = LiteLLMAdminService(
    llm_provider_service=llm_provider_service,
    cost_management_service=cost_management_service,
)
llm_service = LlmService(
    llm_provider_service=llm_provider_service,
    cost_management_service=cost_management_service,
)
chat_service = ChatService(
    retrieval_service=retrieval_service,
    llm_service=llm_service,
)
agent_service = AgentService(
    retrieval_service=retrieval_service,
    registry_service=registry_service,
    skill_service=skill_service,
    llm_provider_service=llm_provider_service,
    cost_management_service=cost_management_service,
)
agent_chat_service = AgentChatService(
    agent_service=agent_service,
    chat_service=chat_service,
    retrieval_service=retrieval_service,
)
trigger_scheduler_service = TriggerSchedulerService(
    agent_service=agent_service,
    registry_service=registry_service,
)
event_dispatcher_service = EventDispatcherService(
    registry_service=registry_service,
)
datasource_service = DatasourceService(space_service=space_service)
mcp_server_service = McpServerService(
    retrieval_service=retrieval_service,
    chat_service=chat_service,
    agent_service=agent_service,
    space_service=space_service,
    registry_service=registry_service,
)
