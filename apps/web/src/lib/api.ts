import type {
  ChatRequest,
  ChatStreamEvent,
  ConversationSummary,
  Message,
  Space,
  AgentSummary,
  MeResponse,
  LlmProvider,
  TenantCredential,
  TenantModelConfig,
  CostBudget,
  UsageAggregate,
  TenantAdminInfo,
  LocalAdminUser,
  RuntimeKeyState,
} from "./types";

const BASE = "/api/v1";

type ApiSpace = {
  id: string;
  name: string;
  slug: string;
};

type ApiAgentSummary = {
  agent_id: string;
  name: string;
  slug: string;
  description?: string;
  status: string;
};

type ApiConversationSummary = {
  id: string;
  title?: string;
  space_ids: string[];
  created_at: string;
  updated_at: string;
};

function authHeaders(): HeadersInit {
  // Token is in httpOnly cookie — credentials: "include" sends it automatically
  // The middleware injects Authorization header for API rewrites
  return {
    "Content-Type": "application/json",
  };
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ─── Me ────────────────────────────────────────────────────────────────────
export async function getMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/me");
}

export async function localLogin(payload: {
  tenant_slug: string;
  email: string;
  password: string;
}): Promise<{ access_token: string; token_type: string }> {
  return apiFetch<{ access_token: string; token_type: string }>("/auth/local/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function provisionTenant(
  payload: Record<string, unknown>,
  bootstrapToken: string
): Promise<{
  tenant_id: string;
  slug: string;
  display_name: string;
  auth_mode: string;
  bootstrap_admin_created: boolean;
}> {
  return apiFetch("/admin/tenants/provision", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      ...authHeaders(),
      "X-Bootstrap-Token": bootstrapToken,
    },
  });
}

export async function getCurrentTenant(): Promise<TenantAdminInfo> {
  return apiFetch<TenantAdminInfo>("/admin/tenants/current");
}

export async function updateCurrentTenantAuth(payload: Record<string, unknown>): Promise<TenantAdminInfo> {
  return apiFetch<TenantAdminInfo>("/admin/tenants/current/auth", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getLocalUsers(): Promise<LocalAdminUser[]> {
  return apiFetch<LocalAdminUser[]>("/admin/tenants/local-users");
}

export async function createLocalUser(payload: Record<string, unknown>): Promise<LocalAdminUser> {
  return apiFetch<LocalAdminUser>("/admin/tenants/local-users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateLocalUser(id: string, payload: Record<string, unknown>): Promise<LocalAdminUser> {
  return apiFetch<LocalAdminUser>(`/admin/tenants/local-users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ─── Spaces ────────────────────────────────────────────────────────────────
export async function getSpaces(): Promise<Space[]> {
  const spaces = await apiFetch<ApiSpace[]>("/spaces");
  return spaces.map((space) => ({
    space_id: space.id,
    name: space.name,
    description: space.slug,
  }));
}

// ─── Agents ────────────────────────────────────────────────────────────────
export async function getAgents(): Promise<AgentSummary[]> {
  return apiFetch<ApiAgentSummary[]>("/agents");
}

export async function getLlmProviders(): Promise<LlmProvider[]> {
  return apiFetch<LlmProvider[]>("/admin/llm/providers");
}

export async function getLlmCredentials(): Promise<TenantCredential[]> {
  return apiFetch<TenantCredential[]>("/admin/llm/credentials");
}

export async function createLlmCredential(payload: Record<string, unknown>): Promise<TenantCredential> {
  return apiFetch<TenantCredential>("/admin/llm/credentials", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getLlmModels(): Promise<TenantModelConfig[]> {
  return apiFetch<TenantModelConfig[]>("/admin/llm/models");
}

export async function createLlmModel(payload: Record<string, unknown>): Promise<TenantModelConfig> {
  return apiFetch<TenantModelConfig>("/admin/llm/models", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getLlmBudgets(): Promise<CostBudget[]> {
  return apiFetch<CostBudget[]>("/admin/llm/budgets");
}

export async function createLlmBudget(payload: Record<string, unknown>): Promise<CostBudget> {
  return apiFetch<CostBudget>("/admin/llm/budgets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getLlmUsage(days = 30): Promise<{ items: UsageAggregate[] }> {
  return apiFetch<{ items: UsageAggregate[] }>(`/admin/llm/usage?days=${days}`);
}

export async function getRuntimeKeyState(): Promise<RuntimeKeyState> {
  return apiFetch<RuntimeKeyState>("/admin/llm/runtime-key");
}

export async function syncRuntimeKey(): Promise<RuntimeKeyState> {
  return apiFetch<RuntimeKeyState>("/admin/llm/runtime-key/sync", {
    method: "POST",
  });
}

// ─── Conversations ─────────────────────────────────────────────────────────
export interface ConversationsPage {
  items: ConversationSummary[];
  next_cursor: string | null;
}

export async function getConversations(cursor?: string): Promise<ConversationsPage> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  const items = await apiFetch<ApiConversationSummary[]>(`/conversations${q}`);
  return {
    items: items.map((item) => ({
      conversation_id: item.id,
      title: item.title,
      last_message_at: item.updated_at,
      message_count: 0,
      active_space_ids: item.space_ids,
    })),
    next_cursor: null,
  };
}

export async function getConversation(id: string): Promise<{ messages: Message[] }> {
  return apiFetch<{ messages: Message[] }>(`/conversations/${id}`);
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${BASE}/conversations/${id}`, {
    method: "DELETE",
    credentials: "include",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
}

export async function getMessages(
  id: string,
  cursor?: string
): Promise<{ items: Message[]; next_cursor: string | null }> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<{ items: Message[]; next_cursor: string | null }>(
    `/conversations/${id}/messages${q}`
  );
}

// ─── File upload ───────────────────────────────────────────────────────────
export interface UploadProgress {
  loaded: number;
  total: number;
}

export function uploadFile(
  spaceId: string,
  file: File,
  onProgress?: (p: UploadProgress) => void
): Promise<{ document_id: string }> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("space_id", spaceId);
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/datasources/upload`);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress({ loaded: e.loaded, total: e.total });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error("Upload network error"));
    xhr.send(formData);
  });
}

// ─── Artifact signed URL ───────────────────────────────────────────────────
export async function getArtifactSignedUrl(artifactId: string): Promise<{ url: string }> {
  return apiFetch<{ url: string }>(`/artifacts/signed-url?ref=${encodeURIComponent(artifactId)}`);
}

// ─── SSE stream chat ───────────────────────────────────────────────────────
export function streamChat(
  request: ChatRequest,
  onEvent: (event: ChatStreamEvent) => void
): () => void {
  let aborted = false;
  let retried = false;
  const controller = new AbortController();

  async function run(req: ChatRequest) {
    const res = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Stream failed ${res.status}: ${text}`);
    }

    if (!res.body) throw new Error("No response body");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done = false;
    let receivedDone = false;

    try {
      while (!done) {
        const { value, done: streamDone } = await reader.read();
        done = streamDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data:")) continue;
            const jsonStr = trimmed.slice(5).trim();
            if (!jsonStr || jsonStr === "[DONE]") continue;

            try {
              const event = JSON.parse(jsonStr) as ChatStreamEvent;
              onEvent(event);
              if (event.type === "done") {
                receivedDone = true;
                done = true;
                break;
              }
            } catch {
              // Malformed line — skip
            }
          }
        }
      }

      if (!receivedDone && !aborted) {
        throw new Error("Stream ended before done event");
      }
    } catch (err) {
      if (aborted) return;
      // Retry once on disconnect before done
      if (!retried) {
        retried = true;
        await run({ ...req });
      } else {
        throw err;
      }
    } finally {
      reader.releaseLock();
    }
  }

  run(request).catch((err) => {
    if (!aborted) {
      onEvent({
        type: "error",
        code: "STREAM_ERROR",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  });

  return () => {
    aborted = true;
    controller.abort();
  };
}
