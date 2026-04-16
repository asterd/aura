"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuraStore } from "@/lib/store";
import { getConversations, getAgents, getSpaces, deleteConversation } from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";
import { CreateSpaceModal } from "./CreateSpaceModal";

const REFRESH_INTERVAL = 5 * 60 * 1000;

/* ─── Date grouping ─────────────────────────── */
function groupByDate(threads: ConversationSummary[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const weekAgo = new Date(todayStart);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const monthAgo = new Date(todayStart);
  monthAgo.setDate(monthAgo.getDate() - 30);

  const today: ConversationSummary[] = [];
  const last7: ConversationSummary[] = [];
  const last30: ConversationSummary[] = [];
  const older: ConversationSummary[] = [];

  for (const t of threads) {
    const d = new Date(t.updated_at);
    if (d >= todayStart) today.push(t);
    else if (d >= weekAgo) last7.push(t);
    else if (d >= monthAgo) last30.push(t);
    else older.push(t);
  }

  return { today, last7, last30, older };
}

/* ─── Icons ─────────────────────────────────── */
function Icon({ path, size = 16 }: { path: string | string[]; size?: number }) {
  const paths = Array.isArray(path) ? path : [path];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

const ICONS = {
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  plus: "M12 5v14M5 12h14",
  folder: ["M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"],
  folderPlus: ["M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z", "M12 11v6M9 14h6"],
  agent: "M12 2a5 5 0 0 1 5 5c0 2.76-2.24 5-5 5S7 9.76 7 7a5 5 0 0 1 5-5zm0 14c5.52 0 10 2.24 10 5v1H2v-1c0-2.76 4.48-5 10-5z",
  settings: ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"],
  trash: ["M3 6h18", "M19 6l-1 14H6L5 6", "M8 6V4h8v2"],
  chevronLeft: "M15 18l-6-6 6-6",
  chevronRight: "M9 18l6-6-6-6",
  search: ["M21 21l-4.35-4.35", "M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"],
  layers: ["M12 2L2 7l10 5 10-5-10-5z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"],
};

/* ─── Thread item ────────────────────────────── */
function ThreadItem({
  thread,
  isActive,
  onDelete,
  collapsed,
}: {
  thread: ConversationSummary;
  isActive: boolean;
  onDelete: (id: string) => void;
  collapsed: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const title = (thread.title ?? "Untitled").slice(0, 45) + ((thread.title?.length ?? 0) > 45 ? "…" : "");

  if (collapsed) {
    return (
      <Link
        href={`/chat/${thread.id}`}
        title={thread.title ?? "Untitled"}
        className="mx-1 my-0.5 flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-150"
        style={{
          backgroundColor: isActive ? "var(--sidebar-item-active)" : "transparent",
          color: isActive ? "var(--accent)" : "var(--text-tertiary)",
        }}
      >
        <Icon path={ICONS.chat} size={14} />
      </Link>
    );
  }

  return (
    <div
      className="group relative mx-1 my-0.5 flex items-center rounded-lg"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Link
        href={`/chat/${thread.id}`}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-3 py-2 text-sm transition-all duration-150"
        style={{
          backgroundColor: isActive ? "var(--sidebar-item-active)" : hovered ? "var(--sidebar-item-hover)" : "transparent",
          color: isActive ? "var(--accent)" : "var(--text-secondary)",
        }}
      >
        <span className="truncate">{title}</span>
      </Link>

      {hovered && (
        <button
          onClick={(e) => { e.preventDefault(); onDelete(thread.id); }}
          className="absolute right-1.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-text-tertiary transition-all hover:bg-danger-subtle hover:text-danger"
          title="Delete"
        >
          <Icon path={ICONS.trash} size={13} />
        </button>
      )}
    </div>
  );
}

/* ─── Section header ─────────────────────────── */
function SectionLabel({ label, collapsed }: { label: string; collapsed: boolean }) {
  if (collapsed) return null;
  return (
    <p className="px-3 pb-0.5 pt-3 text-[10px] font-semibold uppercase tracking-widest text-text-tertiary">
      {label}
    </p>
  );
}

/* ─── Main Sidebar ──────────────────────────── */
export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const {
    threads,
    threadsCursor,
    availableSpaces,
    availableAgents,
    setThreads,
    appendThreads,
    removeThread,
    setAvailableSpaces,
    setAvailableAgents,
  } = useAuraStore();

  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const urlThreadId = pathname?.startsWith("/chat/") ? pathname.replace("/chat/", "") : null;

  const loadInitial = useCallback(async () => {
    try {
      const [convRes, agentsRes, spacesRes] = await Promise.allSettled([
        getConversations(),
        getAgents(),
        getSpaces(),
      ]);
      if (convRes.status === "fulfilled") setThreads(convRes.value.items, convRes.value.next_cursor);
      if (agentsRes.status === "fulfilled") setAvailableAgents(agentsRes.value);
      if (spacesRes.status === "fulfilled") setAvailableSpaces(spacesRes.value);
    } catch { /* silent */ }
  }, [setThreads, setAvailableAgents, setAvailableSpaces]);

  useEffect(() => {
    void loadInitial();
    const interval = setInterval(() => void loadInitial(), REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [loadInitial]);

  useEffect(() => {
    if (showSearch && searchRef.current) searchRef.current.focus();
  }, [showSearch]);

  const handleLoadMore = async () => {
    if (!threadsCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await getConversations(threadsCursor);
      appendThreads(res.items, res.next_cursor);
    } catch { /* ignore */ }
    finally { setLoadingMore(false); }
  };

  const handleDelete = async (id: string) => {
    removeThread(id);
    try { await deleteConversation(id); } catch { /* ignore */ }
    if (urlThreadId === id) router.push("/chat");
  };

  const filteredThreads = searchQuery.trim()
    ? threads.filter((t) => (t.title ?? "").toLowerCase().includes(searchQuery.toLowerCase()))
    : threads;

  const { today, last7, last30, older } = groupByDate(filteredThreads);
  const publishedAgents = availableAgents.filter((a) => a.status === "published");

  /* ─── Sidebar content ─── */
  const sidebarContent = (
    <div className={`flex h-full flex-col ${collapsed ? "w-14" : "w-64"} transition-all duration-200`}>
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between px-3 py-3">
        {!collapsed && (
          <Link href="/chat" className="flex items-center gap-2.5">
            <div
              className="flex h-7 w-7 items-center justify-center rounded-lg"
              style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)" }}
            >
              <Icon path={ICONS.layers} size={14} />
            </div>
            <span className="text-sm font-semibold text-text-primary">AURA</span>
          </Link>
        )}
        {collapsed && (
          <div
            className="mx-auto flex h-7 w-7 items-center justify-center rounded-lg"
            style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)" }}
          >
            <Icon path={ICONS.layers} size={14} />
          </div>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-text-tertiary transition-colors hover:bg-surface-hover hover:text-text-secondary"
            title="Collapse sidebar"
          >
            <Icon path={ICONS.chevronLeft} size={14} />
          </button>
        )}
      </div>

      {/* New chat + search */}
      <div className="px-2 pb-2">
        <Link
          href="/chat"
          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white transition-all hover:opacity-90 active:scale-[0.98] ${collapsed ? "justify-center px-0" : ""}`}
          style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)" }}
          title={collapsed ? "New Chat" : undefined}
        >
          <Icon path={ICONS.plus} size={15} />
          {!collapsed && "New Chat"}
        </Link>

        {!collapsed && (
          <div className="mt-1.5">
            {showSearch ? (
              <div className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-2 px-3 py-1.5">
                <Icon path={ICONS.search} size={13} />
                <input
                  ref={searchRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Escape") { setShowSearch(false); setSearchQuery(""); }}}
                  placeholder="Search conversations…"
                  className="min-w-0 flex-1 bg-transparent text-xs text-text-primary placeholder:text-text-tertiary outline-none"
                />
                <button
                  onClick={() => { setShowSearch(false); setSearchQuery(""); }}
                  className="text-text-tertiary hover:text-text-secondary transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowSearch(true)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-xs text-text-tertiary transition-colors hover:bg-surface-hover hover:text-text-secondary"
              >
                <Icon path={ICONS.search} size={13} />
                Search…
              </button>
            )}
          </div>
        )}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Conversations */}
        {threads.length === 0 && !searchQuery ? (
          !collapsed && (
            <div className="px-3 py-6 text-center">
              <p className="text-xs text-text-tertiary">No conversations yet</p>
              <p className="mt-0.5 text-[11px] text-text-tertiary opacity-60">Start a new chat above</p>
            </div>
          )
        ) : (
          <>
            {today.length > 0 && (
              <>
                <SectionLabel label="Today" collapsed={collapsed} />
                {today.map((t) => (
                  <ThreadItem key={t.id} thread={t} isActive={urlThreadId === t.id} onDelete={handleDelete} collapsed={collapsed} />
                ))}
              </>
            )}
            {last7.length > 0 && (
              <>
                <SectionLabel label="Last 7 days" collapsed={collapsed} />
                {last7.map((t) => (
                  <ThreadItem key={t.id} thread={t} isActive={urlThreadId === t.id} onDelete={handleDelete} collapsed={collapsed} />
                ))}
              </>
            )}
            {last30.length > 0 && (
              <>
                <SectionLabel label="Last 30 days" collapsed={collapsed} />
                {last30.map((t) => (
                  <ThreadItem key={t.id} thread={t} isActive={urlThreadId === t.id} onDelete={handleDelete} collapsed={collapsed} />
                ))}
              </>
            )}
            {older.length > 0 && (
              <>
                <SectionLabel label="Older" collapsed={collapsed} />
                {older.map((t) => (
                  <ThreadItem key={t.id} thread={t} isActive={urlThreadId === t.id} onDelete={handleDelete} collapsed={collapsed} />
                ))}
              </>
            )}

            {threadsCursor && !collapsed && (
              <button
                onClick={() => void handleLoadMore()}
                disabled={loadingMore}
                className="mx-3 my-1 w-[calc(100%-1.5rem)] rounded-lg py-1.5 text-xs text-text-tertiary transition-colors hover:bg-surface-hover"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </>
        )}

        {/* Spaces section */}
        {availableSpaces.length > 0 && (
          <div className="mt-1 border-t border-border-subtle pt-1">
            {!collapsed && (
              <div className="flex items-center justify-between px-3 pb-0.5 pt-3">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-text-tertiary">Spaces</p>
                <button
                  onClick={() => setCreateSpaceOpen(true)}
                  className="flex h-5 w-5 items-center justify-center rounded text-text-tertiary transition-colors hover:bg-surface-hover hover:text-accent"
                  title="Create space"
                >
                  <Icon path={ICONS.plus} size={12} />
                </button>
              </div>
            )}
            {availableSpaces.map((s) => (
              collapsed ? (
                <div
                  key={s.id}
                  title={s.name}
                  className="mx-1 my-0.5 flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition-all hover:bg-surface-hover hover:text-text-secondary"
                >
                  <Icon path={ICONS.folder} size={14} />
                </div>
              ) : (
                <div
                  key={s.id}
                  className="mx-1 my-0.5 flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-xs text-text-secondary transition-all hover:bg-surface-hover cursor-default"
                >
                  <Icon path={ICONS.folder} size={13} />
                  <span className="truncate">{s.name}</span>
                  <span
                    className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase"
                    style={{ background: "var(--surface-3)", color: "var(--text-tertiary)" }}
                  >
                    {s.space_type ?? "doc"}
                  </span>
                </div>
              )
            ))}
          </div>
        )}

        {/* Agents section */}
        {publishedAgents.length > 0 && (
          <div className="mt-1 border-t border-border-subtle pt-1">
            {!collapsed && (
              <p className="px-3 pb-0.5 pt-3 text-[10px] font-semibold uppercase tracking-widest text-text-tertiary">
                Agents
              </p>
            )}
            {publishedAgents.map((a) => (
              collapsed ? (
                <div
                  key={a.agent_id}
                  title={a.name}
                  className="mx-1 my-0.5 flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition-all hover:bg-surface-hover hover:text-text-secondary"
                >
                  <Icon path={ICONS.agent} size={14} />
                </div>
              ) : (
                <div
                  key={a.agent_id}
                  className="mx-1 my-0.5 flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-xs text-text-secondary cursor-default transition-all hover:bg-surface-hover"
                >
                  <div
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded"
                    style={{ background: "var(--accent-subtle)", color: "var(--accent)" }}
                  >
                    <Icon path={ICONS.agent} size={11} />
                  </div>
                  <span className="truncate">{a.name}</span>
                  <div className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-success" title="Published" />
                </div>
              )
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="shrink-0 border-t border-border-subtle px-2 py-2">
        {collapsed ? (
          <>
            <button
              onClick={() => setCollapsed(false)}
              className="mx-auto mb-1.5 flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition-colors hover:bg-surface-hover hover:text-text-secondary"
              title="Expand sidebar"
            >
              <Icon path={ICONS.chevronRight} size={14} />
            </button>
            <Link
              href="/settings"
              className="mx-auto flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition-colors hover:bg-surface-hover hover:text-text-secondary"
              title="Settings"
            >
              <Icon path={ICONS.settings} size={15} />
            </Link>
          </>
        ) : (
          <Link
            href="/settings"
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-text-secondary transition-all hover:bg-surface-hover ${pathname === "/settings" ? "bg-sidebar-item-active text-accent" : ""}`}
          >
            <Icon path={ICONS.settings} size={15} />
            Settings
          </Link>
        )}
      </div>

      <CreateSpaceModal
        open={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={() => void loadInitial()}
      />
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className="hidden md:flex h-full shrink-0 flex-col"
        style={{
          width: collapsed ? "var(--sidebar-collapsed-width)" : "var(--sidebar-width)",
          backgroundColor: "var(--sidebar-bg)",
          borderRight: "1px solid var(--border-subtle)",
          transition: "width 200ms ease",
        }}
      >
        {sidebarContent}
      </aside>

      {/* Mobile: hamburger button */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-4 z-40 flex h-9 w-9 items-center justify-center rounded-xl border border-border-subtle bg-surface-1 text-text-secondary shadow-sm md:hidden"
        aria-label="Open menu"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-bg-overlay"
            onClick={() => setMobileOpen(false)}
          />
          <aside
            className="absolute left-0 top-0 flex h-full w-72 flex-col shadow-xl"
            style={{ backgroundColor: "var(--sidebar-bg)", borderRight: "1px solid var(--border-subtle)" }}
          >
            <div className="absolute right-3 top-3">
              <button
                onClick={() => setMobileOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary hover:bg-surface-hover"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
            {/* Reuse same content but never collapsed on mobile */}
            <div className="flex h-full flex-col" style={{ width: "100%" }}>
              {sidebarContent}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
