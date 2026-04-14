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
  conversation_id: string;
  title?: string;
  last_message_at: string;
  message_count: number;
  active_space_ids: string[];
}

export interface Space {
  space_id: string;
  name: string;
  description?: string;
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
}

export interface MeResponse {
  identity: UserIdentity;
  spaces: string[];
  active_policies: Record<string, unknown>;
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
  stream: true;
}
