import type {
  ChatRequest,
  ChatStreamEvent,
  ConversationSummary,
  Message,
  Space,
  AgentSummary,
  MeResponse,
} from "./types";

const BASE = "/api/v1";

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

// ─── Spaces ────────────────────────────────────────────────────────────────
export async function getSpaces(): Promise<Space[]> {
  return apiFetch<Space[]>("/spaces");
}

// ─── Agents ────────────────────────────────────────────────────────────────
export async function getAgents(): Promise<AgentSummary[]> {
  return apiFetch<AgentSummary[]>("/agents");
}

// ─── Conversations ─────────────────────────────────────────────────────────
export interface ConversationsPage {
  items: ConversationSummary[];
  next_cursor: string | null;
}

export async function getConversations(cursor?: string): Promise<ConversationsPage> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<ConversationsPage>(`/conversations${q}`);
}

export async function getConversation(id: string): Promise<{ messages: Message[] }> {
  return apiFetch<{ messages: Message[] }>(`/conversations/${id}`);
}

export async function deleteConversation(id: string): Promise<void> {
  await apiFetch<void>(`/conversations/${id}`, { method: "DELETE" });
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
  return apiFetch<{ url: string }>(`/artifacts/${artifactId}/signed-url`);
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
