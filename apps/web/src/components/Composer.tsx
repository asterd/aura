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

function notify(type: "success" | "error" | "warning" | "info", message: string, title?: string) {
  window.dispatchEvent(new CustomEvent("aura:toast", { detail: { type, message, title } }));
}

/* ─── File chip ─────────────────────────────── */
function FileChip({ upload, onRemove }: { upload: FileUploadState; onRemove: () => void }) {
  const ext = upload.file.name.split(".").pop()?.toUpperCase() ?? "FILE";
  return (
    <div
      className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs"
      style={{
        background: "var(--surface-2)",
        borderColor: upload.error ? "rgba(239,68,68,0.4)" : "var(--border-subtle)",
        color: upload.error ? "var(--danger)" : "var(--text-secondary)",
      }}
    >
      <span
        className="rounded px-1 py-0.5 text-[9px] font-bold"
        style={{ background: upload.error ? "var(--danger-subtle)" : "var(--accent-subtle)", color: upload.error ? "var(--danger)" : "var(--accent)" }}
      >
        {ext}
      </span>
      <span className="max-w-[100px] truncate">{upload.file.name}</span>
      {!upload.done && !upload.error && (
        <div className="relative h-1.5 w-12 overflow-hidden rounded-full bg-border-subtle">
          <div
            className="absolute left-0 top-0 h-full rounded-full bg-accent transition-all"
            style={{ width: `${upload.progress}%` }}
          />
        </div>
      )}
      {upload.done && (
        <svg className="h-3 w-3 text-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      )}
      <button
        onClick={onRemove}
        className="ml-0.5 flex h-3.5 w-3.5 items-center justify-center rounded text-text-tertiary hover:text-text-secondary"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>
  );
}

/* ─── Main Composer ─────────────────────────── */
export function Composer({ threadId, onNewThread }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [mention, setMention] = useState<MentionState | null>(null);
  const [uploads, setUploads] = useState<FileUploadState[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [draftSpaceIds, setDraftSpaceIds] = useState<string[]>([]);
  const [draftAgentIds, setDraftAgentIds] = useState<string[]>([]);
  const [focused, setFocused] = useState(false);

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

  useEffect(() => {
    getAvailableModels()
      .then(({ allowed_models, default_model }) => setAvailableModels(allowed_models, default_model))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Listen to starter prompt events from ChatArea
  useEffect(() => {
    const handler = (e: Event) => {
      const { prompt } = (e as CustomEvent).detail;
      setText(prompt);
      textareaRef.current?.focus();
    };
    window.addEventListener("aura:starter-prompt", handler);
    return () => window.removeEventListener("aura:starter-prompt", handler);
  }, []);

  const fallbackSpaceIds = availableSpaces.slice(0, 1).map((s) => s.id);
  const currentSpaceIds = threadId
    ? (activeSpaceIds[threadId] ?? fallbackSpaceIds)
    : (draftSpaceIds.length ? draftSpaceIds : fallbackSpaceIds);
  const currentAgentIds = threadId ? (activeAgentIds[threadId] ?? []) : draftAgentIds;

  // Auto-resize
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 220) + "px";
  }, [text]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    if (val.length > MAX_CHARS) return;
    setText(val);

    const cursor = e.target.selectionStart;
    const before = val.slice(0, cursor);
    const atMatch = before.match(/@([\w-]*)$/);
    const hashMatch = before.match(/#([\w-]*)$/);

    if (atMatch) setMention({ type: "agent", query: atMatch[1], start: cursor - atMatch[0].length });
    else if (hashMatch) setMention({ type: "space", query: hashMatch[1], start: cursor - hashMatch[0].length });
    else setMention(null);
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
      const nextIds = Array.from(new Set([...currentAgentIds, (item as AgentSummary).agent_id]));
      if (threadId) setActiveAgentIds(threadId, nextIds);
      else setDraftAgentIds(nextIds);
    } else {
      const nextIds = Array.from(new Set([...currentSpaceIds, (item as Space).id]));
      if (threadId) setActiveSpaceIds(threadId, nextIds);
      else setDraftSpaceIds(nextIds);
    }
    textareaRef.current?.focus();
  };

  const filteredMentions = mention
    ? mention.type === "agent"
      ? availableAgents.filter((a) => a.status === "published" && a.name.toLowerCase().includes(mention.query.toLowerCase()))
      : availableSpaces.filter((s) => s.name.toLowerCase().includes(mention.query.toLowerCase()))
    : [];

  const handleFileInput = (files: FileList | null) => {
    if (!files) return;
    const spaceId = currentSpaceIds[0];
    if (!spaceId) {
      notify("warning", "Select a Knowledge Space before uploading files.");
      return;
    }
    Array.from(files).forEach((file) => {
      setUploads((prev) => [...prev, { file, progress: 0, done: false }]);
      uploadFile(spaceId, file, ({ loaded, total }) => {
        setUploads((prev) => prev.map((u) => u.file === file ? { ...u, progress: Math.round((loaded / total) * 100) } : u));
      })
        .then(({ document_id }) => {
          setUploads((prev) => prev.map((u) => u.file === file ? { ...u, progress: 100, done: true, documentId: document_id } : u));
        })
        .catch((err) => {
          setUploads((prev) => prev.map((u) => u.file === file ? { ...u, error: err.message } : u));
        });
    });
  };

  const handleDragOver = (e: DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: DragEvent) => { e.preventDefault(); setIsDragging(false); handleFileInput(e.dataTransfer.files); };

  const submit = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;

    // Slash commands
    if (trimmed === "/help") {
      notify("info", "Supported commands: /help and /agents.", "AURA commands");
      setText(""); return;
    }
    if (trimmed === "/agents") {
      notify("info", availableAgents.length ? availableAgents.map((a) => `${a.name} (${a.slug})`).join(", ") : "No published agents available.", "Agents");
      setText(""); return;
    }

    setText("");
    setMention(null);

    const conversationId = threadId ?? generateId();
    const userMessageId = generateId();
    const assistantMessageId = generateId();

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
      upsertThread({ id: conversationId, title: trimmed.slice(0, 50), space_ids: currentSpaceIds, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
      setActiveSpaceIds(conversationId, currentSpaceIds);
      setActiveAgentIds(conversationId, currentAgentIds);
      setActiveThread(conversationId);
      onNewThread(conversationId);
    }

    streamChat(
      { conversation_id: conversationId, message: trimmed, space_ids: currentSpaceIds, active_agent_ids: currentAgentIds.length ? currentAgentIds : undefined, model_override: selectedModel ?? undefined, stream: true },
      (event: ChatStreamEvent) => {
        switch (event.type) {
          case "token": appendToken(event.content); break;
          case "citation": addCitation(assistantMessageId, event.citation); break;
          case "agent_running": setAgentRunning(assistantMessageId, event.agent_name, event.run_id); break;
          case "agent_done":
            clearAgentRunning(assistantMessageId);
            for (const ref of event.artifacts ?? []) {
              addArtifact(assistantMessageId, { artifact_id: ref, artifact_type: artifactTypeFromRef(ref), label: artifactLabelFromRef(ref), created_at: new Date().toISOString() });
            }
            break;
          case "done": finalizeMessage(event.message_id || assistantMessageId, event.trace_id); break;
          case "error": setStreamingError(assistantMessageId, `${event.code}: ${event.message}`); break;
        }
      }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, isStreaming, threadId, currentSpaceIds, currentAgentIds, selectedModel]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); }
    if (e.key === "Escape") setMention(null);
  };

  const charCount = text.length;
  const nearLimit = charCount > MAX_CHARS * 0.85;
  const canSend = text.trim().length > 0 && !isStreaming;

  return (
    <div
      className="relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-2xl text-sm font-medium"
          style={{ background: "var(--accent-subtle)", border: "2px dashed var(--accent)", color: "var(--accent)" }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
          </svg>
          Drop files to upload
        </div>
      )}

      {/* Mention dropdown */}
      {mention && filteredMentions.length > 0 && (
        <div
          className="absolute bottom-full left-0 z-30 mb-2 w-64 overflow-hidden rounded-xl border border-border-default bg-surface-1 shadow-xl animate-scale-in"
        >
          <div className="border-b border-border-subtle px-3 py-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
              {mention.type === "agent" ? "Agents" : "Spaces"}
            </span>
          </div>
          {filteredMentions.slice(0, 8).map((item) => {
            const isAgent = mention.type === "agent";
            const key = isAgent ? (item as AgentSummary).agent_id : (item as Space).id;
            const name = isAgent ? (item as AgentSummary).name : (item as Space).name;
            const sub = isAgent ? (item as AgentSummary).description : (item as Space).slug;
            return (
              <button
                key={key}
                onMouseDown={(e) => { e.preventDefault(); insertMention(item, mention.type); }}
                className="flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover"
              >
                <span className="text-sm font-medium text-text-primary">
                  {mention.type === "agent" ? "@" : "#"}{name}
                </span>
                {sub && <span className="w-full truncate text-xs text-text-tertiary">{sub}</span>}
              </button>
            );
          })}
        </div>
      )}

      {/* Main input container */}
      <div
        className="overflow-hidden rounded-2xl border transition-all duration-150"
        style={{
          background: "var(--surface-2)",
          borderColor: focused ? "var(--accent)" : "var(--border-default)",
          boxShadow: focused ? "0 0 0 3px var(--accent-subtle)" : "var(--shadow-xs)",
        }}
      >
        {/* File uploads */}
        {uploads.length > 0 && (
          <div className="flex flex-wrap gap-1.5 border-b border-border-subtle px-3 py-2">
            {uploads.map((u, i) => (
              <FileChip key={i} upload={u} onRemove={() => setUploads((prev) => prev.filter((_, j) => j !== i))} />
            ))}
          </div>
        )}

        {/* Textarea */}
        <div className="px-3 pt-3">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            disabled={isStreaming}
            placeholder={
              isStreaming
                ? "Generating response…"
                : "Message AURA — @ agents, # spaces, / commands"
            }
            rows={1}
            className="w-full resize-none bg-transparent text-sm leading-relaxed text-text-primary outline-none placeholder:text-text-tertiary disabled:opacity-50"
            style={{ maxHeight: "220px", minHeight: "24px" }}
          />
        </div>

        {/* Bottom toolbar */}
        <div className="flex items-center gap-1.5 px-2 py-2">
          {/* Attach */}
          <label
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-text-tertiary transition-colors hover:bg-surface-hover hover:text-text-secondary"
            title="Attach file"
          >
            <input ref={fileInputRef} type="file" multiple className="sr-only" onChange={(e) => handleFileInput(e.target.files)} />
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
            </svg>
          </label>

          {/* Space selector */}
          <SpaceSelector
            spaces={availableSpaces}
            selectedIds={currentSpaceIds}
            onChange={(ids) => { if (threadId) setActiveSpaceIds(threadId, ids); else setDraftSpaceIds(ids); }}
            disabled={isStreaming}
          />

          {/* Model selector */}
          <ModelSelector
            models={availableModels}
            selected={selectedModel}
            defaultModel={defaultModel}
            onChange={setSelectedModel}
            disabled={isStreaming}
          />

          {/* Active agents badge */}
          {currentAgentIds.length > 0 && (
            <span
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium"
              style={{ background: "var(--accent-subtle)", color: "var(--accent)" }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0-16 0"/>
              </svg>
              {currentAgentIds.length} agent{currentAgentIds.length !== 1 ? "s" : ""}
            </span>
          )}

          {/* Char counter */}
          {nearLimit && (
            <span className={`ml-auto text-[10px] ${charCount >= MAX_CHARS ? "text-danger" : "text-text-tertiary"}`}>
              {charCount.toLocaleString()} / {MAX_CHARS.toLocaleString()}
            </span>
          )}

          {/* Spacer */}
          {!nearLimit && <div className="flex-1" />}

          {/* Send / stop button */}
          {isStreaming ? (
            <div className="flex h-8 w-8 items-center justify-center">
              <div className="spinner" />
            </div>
          ) : (
            <button
              onClick={() => void submit()}
              disabled={!canSend}
              title="Send (Enter)"
              className="flex h-8 w-8 items-center justify-center rounded-xl transition-all active:scale-95"
              style={{
                background: canSend ? "linear-gradient(135deg, var(--accent), var(--accent-dark))" : "var(--surface-3)",
                color: canSend ? "white" : "var(--text-tertiary)",
                cursor: canSend ? "pointer" : "not-allowed",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Footer hint */}
      <p className="mt-1.5 text-center text-[11px] text-text-tertiary">
        Press <kbd className="rounded border border-border-subtle bg-surface-3 px-1 py-px font-mono text-[10px]">⏎</kbd> to send &middot; <kbd className="rounded border border-border-subtle bg-surface-3 px-1 py-px font-mono text-[10px]">⇧⏎</kbd> for new line
      </p>
    </div>
  );
}
