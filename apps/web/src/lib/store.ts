import { create } from "zustand";
import type {
  ConversationSummary,
  Message,
  Space,
  AgentSummary,
  Citation,
  ArtifactRef,
} from "./types";

interface AuraStore {
  // Data
  threads: ConversationSummary[];
  threadsCursor: string | null;
  activeThreadId: string | null;
  threadMessages: Record<string, Message[]>;
  streamingMessageId: string | null;
  streamBuffer: string;
  availableSpaces: Space[];
  availableAgents: AgentSummary[];
  activeSpaceIds: Record<string, string[]>;
  activeAgentIds: Record<string, string[]>;
  isStreaming: boolean;

  // Thread actions
  setThreads: (threads: ConversationSummary[], cursor: string | null) => void;
  appendThreads: (threads: ConversationSummary[], cursor: string | null) => void;
  upsertThread: (thread: ConversationSummary) => void;
  removeThread: (id: string) => void;
  setActiveThread: (id: string | null) => void;

  // Message actions
  setMessages: (threadId: string, messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateMessage: (threadId: string, messageId: string, patch: Partial<Message>) => void;

  // Streaming actions
  beginStreaming: (messageId: string) => void;
  appendToken: (token: string) => void;
  addCitation: (messageId: string, citation: Citation) => void;
  addArtifact: (messageId: string, artifact: ArtifactRef) => void;
  setAgentRunning: (messageId: string, agentName: string, runId: string) => void;
  clearAgentRunning: (messageId: string) => void;
  finalizeMessage: (serverMessageId: string, traceId: string) => void;
  setStreamingError: (messageId: string, error: string) => void;
  clearStreaming: () => void;

  // Space / agent config
  setAvailableSpaces: (spaces: Space[]) => void;
  setAvailableAgents: (agents: AgentSummary[]) => void;
  setActiveSpaceIds: (threadId: string, ids: string[]) => void;
  setActiveAgentIds: (threadId: string, ids: string[]) => void;

  // Model selection
  selectedModel: string | null;
  availableModels: string[];
  defaultModel: string;
  setSelectedModel: (model: string | null) => void;
  setAvailableModels: (models: string[], defaultModel: string) => void;
}

export const useAuraStore = create<AuraStore>()((set, get) => ({
  threads: [],
  threadsCursor: null,
  activeThreadId: null,
  threadMessages: {},
  streamingMessageId: null,
  streamBuffer: "",
  availableSpaces: [],
  availableAgents: [],
  activeSpaceIds: {},
  activeAgentIds: {},
  isStreaming: false,

  setThreads: (threads, cursor) =>
    set({ threads, threadsCursor: cursor }),

  appendThreads: (threads, cursor) =>
    set((s) => ({
      threads: [...s.threads, ...threads],
      threadsCursor: cursor,
    })),

  upsertThread: (thread) =>
    set((s) => {
      const exists = s.threads.find(
        (t) => t.conversation_id === thread.conversation_id
      );
      if (exists) {
        return {
          threads: s.threads.map((t) =>
            t.conversation_id === thread.conversation_id ? thread : t
          ),
        };
      }
      return { threads: [thread, ...s.threads] };
    }),

  removeThread: (id) =>
    set((s) => ({
      threads: s.threads.filter((t) => t.conversation_id !== id),
      activeThreadId:
        s.activeThreadId === id ? null : s.activeThreadId,
    })),

  setActiveThread: (id) => set({ activeThreadId: id }),

  setMessages: (threadId, messages) =>
    set((s) => ({
      threadMessages: { ...s.threadMessages, [threadId]: messages },
    })),

  addMessage: (message) =>
    set((s) => {
      const existing = s.threadMessages[message.conversation_id] ?? [];
      return {
        threadMessages: {
          ...s.threadMessages,
          [message.conversation_id]: [...existing, message],
        },
      };
    }),

  updateMessage: (threadId, messageId, patch) =>
    set((s) => {
      const messages = s.threadMessages[threadId] ?? [];
      return {
        threadMessages: {
          ...s.threadMessages,
          [threadId]: messages.map((m) =>
            m.message_id === messageId ? { ...m, ...patch } : m
          ),
        },
      };
    }),

  beginStreaming: (messageId) =>
    set({ streamingMessageId: messageId, streamBuffer: "", isStreaming: true }),

  appendToken: (token) =>
    set((s) => {
      const newBuffer = s.streamBuffer + token;
      // Also update the message content live
      const mid = s.streamingMessageId;
      if (!mid) return { streamBuffer: newBuffer };
      const threadMessages = { ...s.threadMessages };
      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex((m) => m.message_id === mid);
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) =>
            i === idx ? { ...m, content: newBuffer, status: "STREAMING" } : m
          );
          break;
        }
      }
      return { streamBuffer: newBuffer, threadMessages };
    }),

  addCitation: (messageId, citation) =>
    set((s) => {
      const threadMessages = { ...s.threadMessages };
      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex((m) => m.message_id === messageId);
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) =>
            i === idx
              ? { ...m, citations: [...m.citations, citation] }
              : m
          );
          break;
        }
      }
      return { threadMessages };
    }),

  addArtifact: (messageId, artifact) =>
    set((s) => {
      const threadMessages = { ...s.threadMessages };
      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex((m) => m.message_id === messageId);
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) =>
            i === idx
              ? { ...m, artifacts: [...m.artifacts, artifact] }
              : m
          );
          break;
        }
      }
      return { threadMessages };
    }),

  setAgentRunning: (messageId, agentName, runId) =>
    set((s) => {
      const threadMessages = { ...s.threadMessages };
      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex((m) => m.message_id === messageId);
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) =>
            i === idx
              ? { ...m, agent_running: { agent_name: agentName, run_id: runId } }
              : m
          );
          break;
        }
      }
      return { threadMessages };
    }),

  clearAgentRunning: (messageId) =>
    set((s) => {
      const threadMessages = { ...s.threadMessages };
      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex((m) => m.message_id === messageId);
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) => {
            if (i !== idx) return m;
            const { agent_running: _, ...rest } = m;
            return rest as Message;
          });
          break;
        }
      }
      return { threadMessages };
    }),

  finalizeMessage: (serverMessageId, traceId) =>
    set((s) => {
      const threadMessages = { ...s.threadMessages };
      const streamingMessageId = s.streamingMessageId;

      if (streamingMessageId) {
        for (const tid in threadMessages) {
          const idx = threadMessages[tid].findIndex(
            (m) => m.message_id === streamingMessageId
          );
          if (idx !== -1) {
            threadMessages[tid] = threadMessages[tid].map((m, i) => {
              if (i !== idx) return m;
              const { agent_running: _, ...rest } = m;
              return {
                ...rest,
                message_id: serverMessageId,
                status: "DONE",
                trace_id: traceId,
              } as Message;
            });
            return {
              threadMessages,
              isStreaming: false,
              streamingMessageId: null,
              streamBuffer: "",
            };
          }
        }
      }

      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex(
          (m) => m.message_id === serverMessageId
        );
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) =>
            i === idx
              ? { ...m, status: "DONE", trace_id: traceId, message_id: serverMessageId }
              : m
          );
          break;
        }
      }
      return {
        threadMessages,
        isStreaming: false,
        streamingMessageId: null,
        streamBuffer: "",
      };
    }),

  setStreamingError: (messageId, error) =>
    set((s) => {
      const threadMessages = { ...s.threadMessages };
      for (const tid in threadMessages) {
        const idx = threadMessages[tid].findIndex((m) => m.message_id === messageId);
        if (idx !== -1) {
          threadMessages[tid] = threadMessages[tid].map((m, i) =>
            i === idx ? { ...m, status: "ERROR", error } : m
          );
          break;
        }
      }
      return {
        threadMessages,
        isStreaming: false,
        streamingMessageId: null,
        streamBuffer: "",
      };
    }),

  clearStreaming: () =>
    set({ isStreaming: false, streamingMessageId: null, streamBuffer: "" }),

  setAvailableSpaces: (spaces) => set({ availableSpaces: spaces }),
  setAvailableAgents: (agents) => set({ availableAgents: agents }),

  setActiveSpaceIds: (threadId, ids) =>
    set((s) => ({
      activeSpaceIds: { ...s.activeSpaceIds, [threadId]: ids },
    })),

  setActiveAgentIds: (threadId, ids) =>
    set((s) => ({
      activeAgentIds: { ...s.activeAgentIds, [threadId]: ids },
    })),

  selectedModel: null,
  availableModels: [],
  defaultModel: "",
  setSelectedModel: (model) => set({ selectedModel: model }),
  setAvailableModels: (models, defaultModel) => set({ availableModels: models, defaultModel }),
}));
