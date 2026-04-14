"use client";

import {
  useRef,
  useState,
  useCallback,
  useEffect,
  type KeyboardEvent,
  type DragEvent,
  type ChangeEvent,
} from "react";
import { useAuraStore } from "@/lib/store";
import { streamChat, uploadFile, getAvailableModels } from "@/lib/api";
import type { AgentSummary, Space, Message, ChatStreamEvent } from "@/lib/types";
import { SpaceSelector } from "./SpaceSelector";
import { ModelSelector } from "./ModelSelector";

const MAX_CHARS = 32_000;

interface Props {
  threadId: string | null;
  onNewThread: (id: string) => void;
}

interface MentionState {
  type: "agent" | "space";
  query: string;
  start: number;
}

interface FileUploadState {
  file: File;
  progress: number;
  done: boolean;
  error?: string;
  documentId?: string;
}

function generateId() {
  return crypto.randomUUID();
}

function artifactTypeFromRef(ref: string) {
  const lowered = ref.toLowerCase();
  if (lowered.endsWith(".md") || lowered.endsWith(".markdown")) return "markdown" as const;
  if (lowered.endsWith(".json")) return "json" as const;
  if (lowered.endsWith(".csv")) return "csv" as const;
  if (lowered.endsWith(".pdf")) return "pdf_preview" as const;
  if (/\.(png|jpg|jpeg|gif|webp)$/.test(lowered)) return "image" as const;
  if (lowered.includes(".")) return "code" as const;
  return "unknown" as const;
}

function artifactLabelFromRef(ref: string) {
  const segments = ref.split("/");
  return segments[segments.length - 1] || ref;
}

export function Composer({ threadId, onNewThread }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState("");
  const [mention, setMention] = useState<MentionState | null>(null);
  const [uploads, setUploads] = useState<FileUploadState[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [draftSpaceIds, setDraftSpaceIds] = useState<string[]>([]);
  const [draftAgentIds, setDraftAgentIds] = useState<string[]>([]);

  const {
    isStreaming,
    availableAgents,
    availableSpaces,
    activeSpaceIds,
    activeAgentIds,
    addMessage,
    beginStreaming,
    appendToken,
    addCitation,
    addArtifact,
    setAgentRunning,
    clearAgentRunning,
    finalizeMessage,
    setStreamingError,
    upsertThread,
    setActiveThread,
    setActiveSpaceIds,
    setActiveAgentIds,
    selectedModel,
    availableModels,
    defaultModel,
    setSelectedModel,
    setAvailableModels,
  } = useAuraStore();

  // Load available models on mount
  useEffect(() => {
    getAvailableModels()
      .then(({ allowed_models, default_model }) => {
        setAvailableModels(allowed_models, default_model);
      })
      .catch(() => {/* silent fail — model selector hidden */});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fallbackSpaceIds = availableSpaces.slice(0, 1).map((s) => s.space_id);
  const currentSpaceIds = threadId
    ? (activeSpaceIds[threadId] ?? fallbackSpaceIds)
    : (draftSpaceIds.length ? draftSpaceIds : fallbackSpaceIds);
  const currentAgentIds = threadId
    ? (activeAgentIds[threadId] ?? [])
    : draftAgentIds;

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [text]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    if (val.length > MAX_CHARS) return;
    setText(val);

    // Detect @ or # mentions
    const cursor = e.target.selectionStart;
    const before = val.slice(0, cursor);
    const atMatch = before.match(/@([\w-]*)$/);
    const hashMatch = before.match(/#([\w-]*)$/);

    if (atMatch) {
      setMention({ type: "agent", query: atMatch[1], start: cursor - atMatch[0].length });
    } else if (hashMatch) {
      setMention({ type: "space", query: hashMatch[1], start: cursor - hashMatch[0].length });
    } else {
      setMention(null);
    }
  };

  const insertMention = (item: AgentSummary | Space, type: "agent" | "space") => {
    if (!mention) return;
    const label = type === "agent" ? (item as AgentSummary).name : (item as Space).name;
    const prefix = type === "agent" ? "@" : "#";
    const before = text.slice(0, mention.start);
    const after = text.slice(textareaRef.current?.selectionStart ?? mention.start);
    setText(before + prefix + label + " " + after);
    setMention(null);

    if (type === "agent") {
      const nextIds = Array.from(
        new Set([...currentAgentIds, (item as AgentSummary).agent_id])
      );
      if (threadId) {
        setActiveAgentIds(threadId, nextIds);
      } else {
        setDraftAgentIds(nextIds);
      }
    } else {
      const nextIds = Array.from(
        new Set([...currentSpaceIds, (item as Space).space_id])
      );
      if (threadId) {
        setActiveSpaceIds(threadId, nextIds);
      } else {
        setDraftSpaceIds(nextIds);
      }
    }

    textareaRef.current?.focus();
  };

  const filteredMentions = mention
    ? mention.type === "agent"
      ? availableAgents.filter(
          (a) =>
            a.status === "published" &&
            a.name.toLowerCase().includes(mention.query.toLowerCase())
        )
      : availableSpaces.filter((s) =>
          s.name.toLowerCase().includes(mention.query.toLowerCase())
        )
    : [];

  const handleSlashCommand = (cmd: string): boolean => {
    const normalized = cmd.trim().toLowerCase();
    if (normalized === "/help") {
      alert("AURA commands:\n/help — show this\n/clear — clear chat\n/agents — list agents");
      return true;
    }
    if (normalized === "/clear") {
      // Clear optimistically — parent handles navigation
      setText("");
      return true;
    }
    if (normalized === "/agents") {
      alert(
        availableAgents.length
          ? availableAgents.map((a) => `• ${a.name} (${a.slug})`).join("\n")
          : "No published agents available."
      );
      return true;
    }
    return false;
  };

  const handleFileInput = (files: FileList | null) => {
    if (!files) return;
    const spaceId = currentSpaceIds[0];
    if (!spaceId) {
      alert("Select a Knowledge Space (using the space selector below) before uploading files.");
      return;
    }
    Array.from(files).forEach((file) => {
      const id = generateId();
      setUploads((prev) => [...prev, { file, progress: 0, done: false }]);
      uploadFile(spaceId, file, ({ loaded, total }) => {
        setUploads((prev) =>
          prev.map((u) =>
            u.file === file ? { ...u, progress: Math.round((loaded / total) * 100) } : u
          )
        );
      })
        .then(({ document_id }) => {
          setUploads((prev) =>
            prev.map((u) =>
              u.file === file ? { ...u, progress: 100, done: true, documentId: document_id } : u
            )
          );
        })
        .catch((err) => {
          setUploads((prev) =>
            prev.map((u) =>
              u.file === file ? { ...u, error: err.message } : u
            )
          );
        });
      void id;
    });
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileInput(e.dataTransfer.files);
  };

  const submit = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;

    if (trimmed.startsWith("/") && handleSlashCommand(trimmed)) {
      setText("");
      return;
    }

    setText("");
    setMention(null);

    const conversationId = threadId ?? generateId();
    const userMessageId = generateId();
    const assistantMessageId = generateId();

    // Optimistic user message
    const userMsg: Message = {
      message_id: userMessageId,
      conversation_id: conversationId,
      role: "user",
      content: trimmed,
      status: "DONE",
      citations: [],
      artifacts: [],
      created_at: new Date().toISOString(),
    };

    // Pending assistant message
    const assistantMsg: Message = {
      message_id: assistantMessageId,
      conversation_id: conversationId,
      role: "assistant",
      content: "",
      status: "PENDING",
      citations: [],
      artifacts: [],
      created_at: new Date().toISOString(),
    };

    addMessage(userMsg);
    addMessage(assistantMsg);
    beginStreaming(assistantMessageId);

    if (!threadId) {
      upsertThread({
        conversation_id: conversationId,
        title: trimmed.slice(0, 50),
        last_message_at: new Date().toISOString(),
        message_count: 1,
        active_space_ids: currentSpaceIds,
      });
      setActiveSpaceIds(conversationId, currentSpaceIds);
      setActiveAgentIds(conversationId, currentAgentIds);
      setActiveThread(conversationId);
      onNewThread(conversationId);
    }

    const cleanup = streamChat(
      {
        conversation_id: conversationId,
        message: trimmed,
        space_ids: currentSpaceIds,
        active_agent_ids: currentAgentIds.length ? currentAgentIds : undefined,
        model_override: selectedModel ?? undefined,
        stream: true,
      },
      (event: ChatStreamEvent) => {
        switch (event.type) {
          case "token":
            appendToken(event.content);
            break;
          case "citation":
            addCitation(assistantMessageId, event.citation);
            break;
          case "agent_running":
            setAgentRunning(assistantMessageId, event.agent_name, event.run_id);
            break;
          case "agent_done":
            clearAgentRunning(assistantMessageId);
            for (const ref of event.artifacts ?? []) {
              addArtifact(assistantMessageId, {
                artifact_id: ref,
                artifact_type: artifactTypeFromRef(ref),
                label: artifactLabelFromRef(ref),
                created_at: new Date().toISOString(),
              });
            }
            break;
          case "done":
            finalizeMessage(event.message_id || assistantMessageId, event.trace_id);
            break;
          case "error":
            setStreamingError(assistantMessageId, `${event.code}: ${event.message}`);
            break;
        }
      }
    );

    // Cleanup on unmount if still streaming
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    text,
    isStreaming,
    threadId,
    currentSpaceIds,
    currentAgentIds,
    addMessage,
    beginStreaming,
    addCitation,
    addArtifact,
    appendToken,
    clearAgentRunning,
    finalizeMessage,
    onNewThread,
    setActiveAgentIds,
    setActiveSpaceIds,
    setActiveThread,
    setAgentRunning,
    setStreamingError,
    upsertThread,
  ]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
    if (e.key === "Escape") {
      setMention(null);
    }
  };

  const charCount = text.length;
  const nearLimit = charCount > MAX_CHARS * 0.9;

  return (
    <div
      className="relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div
          className="absolute inset-0 z-20 flex items-center justify-center rounded-xl text-sm font-medium"
          style={{
            backgroundColor: "rgba(99,102,241,0.15)",
            border: "2px dashed var(--accent)",
            color: "var(--accent)",
          }}
        >
          Drop files to upload
        </div>
      )}

      {/* Mention dropdown */}
      {mention && filteredMentions.length > 0 && (
        <div
          className="absolute bottom-full mb-2 left-0 w-64 rounded-xl shadow-xl overflow-hidden z-30"
          style={{
            backgroundColor: "var(--surface-raised)",
            border: "1px solid var(--border)",
          }}
        >
          {filteredMentions.slice(0, 8).map((item) => {
            const isAgent = mention.type === "agent";
            const key = isAgent
              ? (item as AgentSummary).agent_id
              : (item as Space).space_id;
            const name = isAgent
              ? (item as AgentSummary).name
              : (item as Space).name;
            const sub = isAgent
              ? (item as AgentSummary).description
              : (item as Space).description;
            return (
              <button
                key={key}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertMention(item, mention.type);
                }}
                className="w-full flex flex-col items-start px-3 py-2 text-left hover:opacity-80 transition-opacity"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
                  {mention.type === "agent" ? "@" : "#"}
                  {name}
                </span>
                {sub && (
                  <span className="text-xs truncate w-full" style={{ color: "var(--muted-foreground)" }}>
                    {sub}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* File uploads */}
      {uploads.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {uploads.map((u, i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-2 py-1 rounded-lg text-xs"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: `1px solid ${u.error ? "rgba(239,68,68,0.5)" : "var(--border)"}`,
                color: u.error ? "#ef4444" : "var(--foreground)",
              }}
            >
              <span className="max-w-[120px] truncate">{u.file.name}</span>
              {!u.done && !u.error && (
                <span style={{ color: "var(--accent)" }}>{u.progress}%</span>
              )}
              {u.done && (
                <svg className="w-3 h-3" fill="none" stroke="#22c55e" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              )}
              {u.error && <span>{u.error}</span>}
              <button
                onClick={() => setUploads((prev) => prev.filter((_, j) => j !== i))}
                className="ml-1 opacity-60 hover:opacity-100"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Space selector + active agents toolbar */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <SpaceSelector
          spaces={availableSpaces}
          selectedIds={currentSpaceIds}
          onChange={(ids) => {
            if (threadId) {
              setActiveSpaceIds(threadId, ids);
            } else {
              setDraftSpaceIds(ids);
            }
          }}
          disabled={isStreaming}
        />
        <ModelSelector
          models={availableModels}
          selected={selectedModel}
          defaultModel={defaultModel}
          onChange={setSelectedModel}
          disabled={isStreaming}
        />
        {currentAgentIds.length > 0 && (
          <span
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs"
            style={{
              backgroundColor: "var(--surface-raised)",
              border: "1px solid var(--border)",
              color: "var(--muted-foreground)",
            }}
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18" />
            </svg>
            {currentAgentIds.length} agent{currentAgentIds.length !== 1 ? "s" : ""} active
          </span>
        )}
      </div>

      {/* Main composer */}
      <div
        className="flex items-end gap-2 rounded-xl px-3 py-2"
        style={{
          backgroundColor: "var(--surface)",
          border: `1px solid ${isStreaming ? "var(--accent)" : "var(--border)"}`,
          transition: "border-color 0.2s",
        }}
      >
        {/* File upload button */}
        <label
          className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg cursor-pointer transition-colors hover:opacity-80"
          style={{ color: "var(--muted-foreground)" }}
          title="Attach file"
        >
          <input
            type="file"
            multiple
            className="sr-only"
            onChange={(e) => handleFileInput(e.target.files)}
          />
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
          </svg>
        </label>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={
            isStreaming
              ? "Waiting for response..."
              : currentSpaceIds.length > 0
              ? "Message AURA — @ for agents, # for spaces, / for commands"
              : "Free chat — no knowledge space active. Use @ for agents, # to add a space."
          }
          disabled={isStreaming}
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm outline-none leading-relaxed"
          style={{
            color: "var(--foreground)",
            maxHeight: 200,
            minHeight: 24,
            opacity: isStreaming ? 0.5 : 1,
          }}
        />

        {/* Char counter + submit */}
        <div className="flex-shrink-0 flex items-center gap-2">
          {nearLimit && (
            <span className="text-xs" style={{ color: charCount >= MAX_CHARS ? "#ef4444" : "var(--muted-foreground)" }}>
              {charCount}/{MAX_CHARS}
            </span>
          )}

          {isStreaming ? (
            <div
              className="w-8 h-8 flex items-center justify-center rounded-lg"
              style={{ color: "var(--accent)" }}
            >
              <span className="spinner" />
            </div>
          ) : (
            <button
              onClick={() => void submit()}
              disabled={!text.trim() || isStreaming}
              className="w-8 h-8 flex items-center justify-center rounded-lg transition-opacity"
              style={{
                backgroundColor: text.trim() ? "var(--accent)" : "var(--surface-raised)",
                color: text.trim() ? "var(--accent-foreground)" : "var(--muted-foreground)",
                opacity: text.trim() ? 1 : 0.5,
              }}
              title="Send (Enter)"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <p className="text-center text-[10px] mt-1" style={{ color: "var(--muted-foreground)" }}>
        AURA may make mistakes. Verify important information.
      </p>
    </div>
  );
}
