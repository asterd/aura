export interface Citation {
  citation_id: string;
  document_id: string;
  title: string;
  source_system: string;
  source_path: string;
  source_url?: string;
  page_or_section?: string;
  score: number;
  snippet: string;
}

export interface ArtifactRef {
  artifact_id: string;
  artifact_type: "markdown" | "code" | "csv" | "json" | "pdf_preview" | "image" | "unknown";
  label?: string;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title?: string;
  space_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface Space {
  id: string;
  name: string;
  slug: string;
}

export interface AgentSummary {
  agent_id: string;
  name: string;
  slug: string;
  description?: string;
  status: string;
}

export type MessageRole = "user" | "assistant" | "agent";
export type MessageStatus = "PENDING" | "STREAMING" | "DONE" | "ERROR";

export interface Message {
  message_id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  citations: Citation[];
  artifacts: ArtifactRef[];
  error?: string;
  trace_id?: string;
  created_at: string;
  agent_running?: { agent_name: string; run_id: string };
}

export interface UserIdentity {
  user_id: string;
  email: string;
  tenant_id: string;
  roles: string[];
  display_name?: string;
}

export interface MeResponse {
  identity: UserIdentity;
  spaces: string[];
  active_policies: Record<string, unknown>;
}

export interface TenantAdminInfo {
  tenant_id: string;
  slug: string;
  display_name: string;
  auth_mode: string;
  okta_org_id?: string;
  okta_jwks_url?: string;
  okta_issuer?: string;
  okta_audience?: string;
  status: string;
}

export interface PublicTenantInfo {
  tenant_id: string;
  slug: string;
  display_name: string;
  auth_mode: string;
  status: string;
  supports_password_login: boolean;
  okta_issuer?: string;
}

export interface LocalAdminUser {
  id: string;
  email: string;
  display_name?: string;
  roles: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LlmProvider {
  id: string;
  provider_key: string;
  display_name: string;
  description?: string;
  supports_chat: boolean;
  supports_embeddings: boolean;
  supports_reasoning: boolean;
  supports_tools: boolean;
  base_url_hint?: string;
  status: string;
}

export interface TenantCredential {
  id: string;
  provider_id: string;
  provider_key: string;
  name: string;
  secret_ref: string;
  endpoint_override?: string;
  is_default: boolean;
  status: string;
}

export interface TenantModelConfig {
  id: string;
  provider_id: string;
  provider_key: string;
  credential_id: string;
  credential_name: string;
  task_type: string;
  model_name: string;
  alias?: string;
  litellm_model_name?: string;
  input_cost_per_1k?: number;
  output_cost_per_1k?: number;
  rate_limit_rpm?: number;
  concurrency_limit?: number;
  is_default: boolean;
  status: string;
}

export interface CostBudget {
  id: string;
  scope_type: string;
  scope_ref: string;
  provider_id?: string;
  model_name?: string;
  window: string;
  soft_limit_usd?: number;
  hard_limit_usd: number;
  action_on_hard_limit: string;
  is_active: boolean;
}

export interface UsageAggregate {
  provider_id: string;
  provider_key: string;
  model_name: string;
  task_type: string;
  user_id?: string;
  space_id?: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface RuntimeKeyState {
  key_name: string;
  models: string[];
  max_budget_usd?: number;
  rpm_limit?: number;
  synced: boolean;
  sync_mode: string;
  error?: string;
}

export type ChatStreamEvent =
  | { type: "token"; content: string }
  | { type: "citation"; citation: Citation }
  | { type: "done"; message_id: string; trace_id: string }
  | { type: "error"; code: string; message: string }
  | { type: "agent_running"; agent_name: string; run_id: string }
  | { type: "agent_done"; agent_name: string; run_id: string; status: "succeeded" | "failed"; artifacts: string[] };

export interface ChatRequest {
  conversation_id?: string;
  message: string;
  space_ids: string[];
  active_agent_ids?: string[];
  model_override?: string;
  stream: true;
}

export interface AgentVersion {
  id: string;
  name: string;
  version: string;
  status: "draft" | "published" | "archived";
  agent_type: string;
  entrypoint: string;
}

export interface AgentUploadResult extends AgentVersion {}

export interface AvailableModels {
  default_model: string;
  allowed_models: string[];
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKeyInfo {
  raw_key: string;
}
