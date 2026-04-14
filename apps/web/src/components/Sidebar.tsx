"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuraStore } from "@/lib/store";
import {
  getConversations,
  getAgents,
  getSpaces,
  deleteConversation,
} from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";

const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 min

function groupByDate(threads: ConversationSummary[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const weekAgo = new Date(todayStart);
  weekAgo.setDate(weekAgo.getDate() - 7);

  const today: ConversationSummary[] = [];
  const last7: ConversationSummary[] = [];
  const older: ConversationSummary[] = [];

  for (const t of threads) {
    const d = new Date(t.last_message_at);
    if (d >= todayStart) today.push(t);
    else if (d >= weekAgo) last7.push(t);
    else older.push(t);
  }

  return { today, last7, older };
}

interface ThreadItemProps {
  thread: ConversationSummary;
  isActive: boolean;
  onDelete: (id: string) => void;
}

function ThreadItem({ thread, isActive, onDelete }: ThreadItemProps) {
  const [showDelete, setShowDelete] = useState(false);

  const title =
    (thread.title ?? "Untitled conversation").slice(0, 50) +
    ((thread.title?.length ?? 0) > 50 ? "…" : "");

  return (
    <div
      className="group relative flex items-center"
      onMouseEnter={() => setShowDelete(true)}
      onMouseLeave={() => setShowDelete(false)}
    >
      <Link
        href={`/chat/${thread.conversation_id}`}
        className="flex-1 min-w-0 flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors hover:opacity-80"
        style={{
          backgroundColor: isActive ? "var(--surface-raised)" : "transparent",
          color: isActive ? "var(--foreground)" : "var(--muted-foreground)",
          borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
        }}
      >
        <span className="truncate">{title}</span>
      </Link>

      {showDelete && (
        <button
          onClick={(e) => {
            e.preventDefault();
            onDelete(thread.conversation_id);
          }}
          className="absolute right-1 flex-shrink-0 p-1 rounded opacity-60 hover:opacity-100 transition-opacity"
          style={{ color: "var(--muted-foreground)" }}
          title="Delete conversation"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      )}
    </div>
  );
}

interface GroupSectionProps {
  label: string;
  threads: ConversationSummary[];
  activeThreadId: string | null;
  onDelete: (id: string) => void;
}

function GroupSection({ label, threads, activeThreadId, onDelete }: GroupSectionProps) {
  if (!threads.length) return null;
  return (
    <div className="mb-3">
      <p
        className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: "var(--muted-foreground)" }}
      >
        {label}
      </p>
      {threads.map((t) => (
        <ThreadItem
          key={t.conversation_id}
          thread={t}
          isActive={activeThreadId === t.conversation_id}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const {
    threads,
    threadsCursor,
    activeThreadId,
    availableSpaces,
    availableAgents,
    setThreads,
    appendThreads,
    removeThread,
    setAvailableSpaces,
    setAvailableAgents,
  } = useAuraStore();

  const [loadingMore, setLoadingMore] = useState(false);

  // Extract active thread from URL
  const urlThreadId = pathname?.startsWith("/chat/")
    ? pathname.replace("/chat/", "")
    : null;

  const loadInitial = useCallback(async () => {
    try {
      const [convRes, agentsRes, spacesRes] = await Promise.allSettled([
        getConversations(),
        getAgents(),
        getSpaces(),
      ]);

      if (convRes.status === "fulfilled") {
        setThreads(convRes.value.items, convRes.value.next_cursor);
      }
      if (agentsRes.status === "fulfilled") {
        setAvailableAgents(agentsRes.value);
      }
      if (spacesRes.status === "fulfilled") {
        setAvailableSpaces(spacesRes.value);
      }
    } catch {
      // Silently fail — sidebar still renders
    }
  }, [setThreads, setAvailableAgents, setAvailableSpaces]);

  useEffect(() => {
    void loadInitial();
    const interval = setInterval(() => {
      void loadInitial();
    }, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [loadInitial]);

  const handleLoadMore = async () => {
    if (!threadsCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await getConversations(threadsCursor);
      appendThreads(res.items, res.next_cursor);
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  };

  const handleDelete = async (id: string) => {
    removeThread(id);
    try {
      await deleteConversation(id);
    } catch {
      // Already removed from UI — don't re-add
    }
    if (urlThreadId === id) {
      router.push("/chat");
    }
  };

  const { today, last7, older } = groupByDate(threads);

  return (
    <aside
      className="flex flex-col h-full w-64 flex-shrink-0"
      style={{
        backgroundColor: "var(--surface)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-2 px-4 py-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold"
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
        >
          A
        </div>
        <span className="font-semibold text-sm" style={{ color: "var(--foreground)" }}>
          AURA
        </span>
      </div>

      {/* New chat */}
      <div className="px-3 py-3">
        <Link
          href="/chat"
          className="flex items-center justify-center gap-2 w-full py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-80"
          style={{
            backgroundColor: "var(--accent)",
            color: "var(--accent-foreground)",
          }}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </Link>
      </div>

      {/* Thread history */}
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {threads.length === 0 ? (
          <p
            className="px-3 py-4 text-xs text-center"
            style={{ color: "var(--muted-foreground)" }}
          >
            No conversations yet
          </p>
        ) : (
          <>
            <GroupSection
              label="Today"
              threads={today}
              activeThreadId={urlThreadId}
              onDelete={handleDelete}
            />
            <GroupSection
              label="Last 7 Days"
              threads={last7}
              activeThreadId={urlThreadId}
              onDelete={handleDelete}
            />
            <GroupSection
              label="Older"
              threads={older}
              activeThreadId={urlThreadId}
              onDelete={handleDelete}
            />

            {threadsCursor && (
              <button
                onClick={() => void handleLoadMore()}
                disabled={loadingMore}
                className="w-full py-2 text-xs text-center transition-opacity hover:opacity-80"
                style={{ color: "var(--muted-foreground)" }}
              >
                {loadingMore ? "Loading..." : "Load more"}
              </button>
            )}
          </>
        )}

        {/* Spaces */}
        {availableSpaces.length > 0 && (
          <div className="mt-3 mb-2" style={{ borderTop: "1px solid var(--border)" }}>
            <p
              className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--muted-foreground)" }}
            >
              Spaces
            </p>
            {availableSpaces.map((s) => (
              <div
                key={s.space_id}
                className="flex items-center gap-2 px-3 py-1.5 text-xs"
                style={{ color: "var(--muted-foreground)" }}
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                <span className="truncate">{s.name}</span>
              </div>
            ))}
          </div>
        )}

        {/* Agents */}
        {availableAgents.length > 0 && (
          <div className="mb-2" style={{ borderTop: "1px solid var(--border)" }}>
            <p
              className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--muted-foreground)" }}
            >
              Agents
            </p>
            {availableAgents
              .filter((a) => a.status === "published")
              .map((a) => (
                <div
                  key={a.agent_id}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs"
                  style={{ color: "var(--muted-foreground)" }}
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
                  </svg>
                  <span className="truncate">{a.name}</span>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Bottom settings */}
      <div
        className="px-3 py-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link
          href="/settings"
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-opacity hover:opacity-80"
          style={{ color: "var(--muted-foreground)" }}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Settings
        </Link>
      </div>
    </aside>
  );
}
