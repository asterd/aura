"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getAgents, getConversations, getMe, getSpaces } from "@/lib/api";
import { useAuraStore } from "@/lib/store";
import type { ConversationSummary } from "@/lib/types";
import { Avatar, Badge, Button, Input } from "@/components/ui";
import { Icon } from "@/components/icons";

type Section = "chat" | "projects" | "spaces" | "agents" | "admin" | "profile";

const PUBLIC_PATHS = ["/", "/login"];

const PROJECTS = [
  { name: "North Star", spaces: 4, agents: 2, slug: "north-star" },
  { name: "Customer Ops", spaces: 3, agents: 1, slug: "customer-ops" },
  { name: "Knowledge Hub", spaces: 7, agents: 5, slug: "knowledge-hub" },
];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.includes(pathname) || pathname.startsWith("/tenant/");
}

function groupByDate(threads: ConversationSummary[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const weekStart = new Date(todayStart);
  weekStart.setDate(weekStart.getDate() - 7);
  const monthStart = new Date(todayStart);
  monthStart.setDate(monthStart.getDate() - 30);

  return {
    today: threads.filter((thread) => new Date(thread.updated_at) >= todayStart),
    yesterday: threads.filter((thread) => {
      const date = new Date(thread.updated_at);
      return date >= yesterdayStart && date < todayStart;
    }),
    last7: threads.filter((thread) => {
      const date = new Date(thread.updated_at);
      return date >= weekStart && date < yesterdayStart;
    }),
    last30: threads.filter((thread) => {
      const date = new Date(thread.updated_at);
      return date >= monthStart && date < weekStart;
    }),
    older: threads.filter((thread) => new Date(thread.updated_at) < monthStart),
  };
}

function sectionFromPath(pathname: string): Section {
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/settings")) return "profile";
  return "chat";
}

function panelTitle(section: Section) {
  switch (section) {
    case "projects":
      return "Progetti";
    case "spaces":
      return "Spaces";
    case "agents":
      return "Agents";
    case "admin":
      return "Admin";
    case "profile":
      return "Profilo";
    case "chat":
    default:
      return "Chat";
  }
}

function RailItem({
  active,
  label,
  icon,
  onClick,
  href,
  adminOnly,
  visible,
}: {
  active: boolean;
  label: string;
  icon: ReactNode;
  onClick?: () => void;
  href?: string;
  adminOnly?: boolean;
  visible?: boolean;
}) {
  if (visible === false) return null;
  const classes =
    "group relative flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-150";
  const content = (
    <>
      <span
        className={`absolute inset-0 rounded-xl transition-colors ${active ? "bg-[color:var(--accent-subtle)]" : "bg-transparent group-hover:bg-[color:var(--surface-hover)]"}`}
      />
      <span className={`relative flex items-center justify-center ${active ? "text-[color:var(--accent)]" : "text-[color:var(--text-secondary)]"}`}>
        {icon}
      </span>
      {active ? (
        <span className="absolute right-0 top-1/2 h-1.5 w-1.5 -translate-y-1/2 translate-x-[6px] rounded-full bg-[linear-gradient(135deg,var(--brand-primary),var(--brand-secondary))]" />
      ) : null}
    </>
  );

  if (href) {
    return (
      <Link href={href} title={label} className={classes}>
        {content}
      </Link>
    );
  }

  return (
    <button type="button" title={label} onClick={onClick} className={classes} aria-label={label} data-admin-only={adminOnly ? "true" : undefined}>
      {content}
    </button>
  );
}

function SectionLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors ${active ? "bg-[color:var(--accent-subtle)] text-[color:var(--accent)]" : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"}`}
    >
      <span>{label}</span>
      <Icon name="chevron-right" className="h-3.5 w-3.5" />
    </Link>
  );
}

function SectionPanel({
  section,
  onOpenProfile,
  isAdmin,
  mobileOpen,
  onClose,
  embedded = false,
}: {
  section: Section;
  onOpenProfile: () => void;
  isAdmin: boolean;
  mobileOpen: boolean;
  onClose: () => void;
  embedded?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    threads,
    availableAgents,
    availableSpaces,
    setThreads,
    setAvailableAgents,
    setAvailableSpaces,
  } = useAuraStore();
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [threadRes, agentRes, spaceRes] = await Promise.allSettled([
        getConversations(),
        getAgents(),
        getSpaces(),
      ]);

      if (cancelled) return;
      if (threadRes.status === "fulfilled") setThreads(threadRes.value.items, threadRes.value.next_cursor);
      if (agentRes.status === "fulfilled") setAvailableAgents(agentRes.value);
      if (spaceRes.status === "fulfilled") setAvailableSpaces(spaceRes.value);
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [setAvailableAgents, setAvailableSpaces, setThreads]);

  const filteredThreads = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return threads;
    return threads.filter((thread) => (thread.title ?? "Untitled").toLowerCase().includes(value));
  }, [query, threads]);

  const groups = groupByDate(filteredThreads);
  const chatGroups: Array<[string, ConversationSummary[]]> = [
    ["Oggi", groups.today],
    ["Ieri", groups.yesterday],
    ["Ultimi 7 giorni", groups.last7],
    ["Mese scorso", groups.last30],
    ["Più vecchi", groups.older],
  ];
  const currentSection = section;

  return (
    <aside
      className={`${embedded ? "relative w-full border-0 bg-transparent backdrop-blur-0 shadow-none" : "fixed left-[44px] top-0 z-30 h-full w-[240px] border-r border-[color:var(--border)] bg-[color:var(--surface-1)]/95 backdrop-blur-xl"} transition-transform duration-[250ms] ${mobileOpen ? "translate-x-0" : embedded ? "translate-y-0" : "-translate-x-full"}`}
      style={embedded ? undefined : { boxShadow: "var(--shadow-lg)" }}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-[color:var(--border)] px-4 py-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
              {panelTitle(currentSection)}
            </p>
            <p className="mt-1 text-sm font-medium text-[color:var(--text-primary)]">
              {currentSection === "admin" ? "Navigation tree" : "Context panel"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)] md:hidden"
          >
            <Icon name="chevron-down" className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3">
          {currentSection === "chat" ? (
            <div className="space-y-4">
              <Button className="w-full" onClick={() => router.push("/chat")}>
                <Icon name="plus" className="h-4 w-4" />
                New Chat
              </Button>
              <div className="relative">
                <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--text-tertiary)]" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Cerca conversazioni"
                  className="pl-9"
                />
              </div>
              <div className="space-y-3">
                {chatGroups.map(([label, threadsForGroup]) => {
                  if (threadsForGroup.length === 0) return null;
                  return (
                    <div key={label} className="space-y-2">
                      <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
                        {label}
                      </p>
                      <div className="space-y-1">
                        {threadsForGroup.map((thread) => (
                          <Link
                            key={thread.id}
                            href={`/chat/${thread.id}`}
                            className={`group flex items-start justify-between rounded-xl px-3 py-2 text-left transition-colors ${pathname === `/chat/${thread.id}` ? "bg-[color:var(--accent-subtle)] text-[color:var(--accent)]" : "hover:bg-[color:var(--surface-hover)]"}`}
                          >
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium text-[color:var(--text-primary)]">
                                {thread.title ?? "Untitled"}
                              </p>
                              <p className="mt-1 text-[11px] text-[color:var(--text-tertiary)]">
                                {new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short" }).format(new Date(thread.updated_at))}
                              </p>
                            </div>
                            <Icon name="trash" className="mt-1 h-3.5 w-3.5 text-transparent transition-colors group-hover:text-[color:var(--danger)]" />
                          </Link>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-2)] px-3 py-3 text-xs text-[color:var(--text-secondary)]">
                Shortcut globale: <span className="font-mono text-[color:var(--text-primary)]">⌘K</span>
              </div>
            </div>
          ) : null}

          {currentSection === "projects" ? (
            <div className="space-y-3">
              <Button className="w-full">
                <Icon name="plus" className="h-4 w-4" />
                Nuovo Progetto
              </Button>
              {PROJECTS.map((project) => (
                <Link
                  key={project.slug}
                  href="/chat"
                  className="block rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] p-3 transition-colors hover:bg-[color:var(--surface-hover)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-[color:var(--text-primary)]">{project.name}</p>
                      <p className="mt-1 text-[11px] text-[color:var(--text-tertiary)]">project / {project.slug}</p>
                    </div>
                    <Icon name="chevron-right" className="mt-0.5 h-4 w-4 text-[color:var(--text-tertiary)]" />
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Badge>{project.spaces} spaces</Badge>
                    <Badge tone="accent">{project.agents} agents</Badge>
                  </div>
                </Link>
              ))}
            </div>
          ) : null}

          {currentSection === "spaces" ? (
            <div className="space-y-3">
              <Button className="w-full">
                <Icon name="plus" className="h-4 w-4" />
                Nuovo Space
              </Button>
              <div className="space-y-2">
                {availableSpaces.map((space) => (
                  <div key={space.id} className="flex items-center justify-between rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-[color:var(--text-primary)]">{space.name}</p>
                      <p className="mt-1 text-[11px] text-[color:var(--text-tertiary)]">{space.slug}</p>
                    </div>
                    <Badge tone="neutral">{space.space_type ?? "doc"}</Badge>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {currentSection === "agents" ? (
            <div className="space-y-2">
              {availableAgents.map((agent) => (
                <div key={agent.agent_id} className="flex items-center justify-between rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[color:var(--text-primary)]">{agent.name}</p>
                    <p className="mt-1 text-[11px] text-[color:var(--text-tertiary)]">{agent.slug}</p>
                  </div>
                  <Badge tone={agent.status === "published" ? "success" : "neutral"}>{agent.status}</Badge>
                </div>
              ))}
            </div>
          ) : null}

          {currentSection === "admin" ? (
            <div className="space-y-4">
              <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-2)] p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">Overview</p>
                <div className="mt-2 space-y-1">
                  <SectionLink href="/admin/overview" label="Dashboard" active={pathname === "/admin/overview"} />
                </div>
              </div>
              <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">LLM</p>
                <div className="mt-2 space-y-1">
                  <SectionLink href="/admin/llm/providers" label="Providers" active={pathname === "/admin/llm/providers"} />
                  <SectionLink href="/admin/llm/credentials" label="Credentials" active={pathname === "/admin/llm/credentials"} />
                  <SectionLink href="/admin/llm/models" label="Models" active={pathname === "/admin/llm/models"} />
                  <SectionLink href="/admin/llm/budgets" label="Budgets" active={pathname === "/admin/llm/budgets"} />
                </div>
              </div>
              <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">Tenant</p>
                <div className="mt-2 space-y-1">
                  <SectionLink href="/admin/users" label="Utenti locali" active={pathname === "/admin/users"} />
                  <SectionLink href="/admin/tenant/config" label="Configurazione" active={pathname === "/admin/tenant/config"} />
                  <SectionLink href="/admin/tenant/branding" label="Branding" active={pathname === "/admin/tenant/branding"} />
                  <SectionLink href="/admin/tenant/auth" label="Autenticazione" active={pathname === "/admin/tenant/auth"} />
                </div>
              </div>
              <div className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">Operations</p>
                <div className="mt-2 space-y-1">
                  <SectionLink href="/admin/agents" label="Registry" active={pathname === "/admin/agents"} />
                  <SectionLink href="/admin/api-keys" label="Workspace Keys" active={pathname === "/admin/api-keys"} />
                </div>
              </div>
            </div>
          ) : null}

          {currentSection === "profile" ? (
            <div className="space-y-3">
              <Button className="w-full" onClick={onOpenProfile}>
                <Icon name="settings" className="h-4 w-4" />
                Impostazioni account
              </Button>
              <SectionLink href="/settings/profile" label="Profilo" active={pathname === "/settings/profile"} />
              <SectionLink href="/settings/appearance" label="Aspetto" active={pathname === "/settings/appearance"} />
              <SectionLink href="/settings/api-keys" label="API Keys" active={pathname === "/settings/api-keys"} />
              {isAdmin ? <SectionLink href="/admin/overview" label="Amministrazione" active={pathname.startsWith("/admin")} /> : null}
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function BottomTabBar({
  onOpenPanel,
  onOpenProfile,
  isAdmin,
}: {
  onOpenPanel: (section: Section) => void;
  onOpenProfile: () => void;
  isAdmin: boolean;
}) {
  const pathname = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-[color:var(--border)] bg-[color:var(--surface-1)]/95 px-3 pb-[calc(env(safe-area-inset-bottom)+0.5rem)] pt-2 backdrop-blur-xl md:hidden">
      <div className="grid grid-cols-4 gap-2">
        <button onClick={() => onOpenPanel("chat")} className={`flex flex-col items-center gap-1 rounded-2xl py-2 text-[11px] ${pathname.startsWith("/chat") ? "text-[color:var(--accent)]" : "text-[color:var(--text-tertiary)]"}`}>
          <Icon name="message-square" className="h-5 w-5" />
          Chat
        </button>
        <button onClick={() => onOpenPanel("projects")} className="flex flex-col items-center gap-1 rounded-2xl py-2 text-[11px] text-[color:var(--text-tertiary)]">
          <Icon name="folder-open" className="h-5 w-5" />
          Progetti
        </button>
        <button onClick={() => onOpenPanel("chat")} className="flex flex-col items-center gap-1 rounded-2xl py-2 text-[11px] text-[color:var(--text-tertiary)]">
          <Icon name="search" className="h-5 w-5" />
          Cerca
        </button>
        <button onClick={onOpenProfile} className={`relative flex flex-col items-center gap-1 rounded-2xl py-2 text-[11px] ${pathname.startsWith("/settings") ? "text-[color:var(--accent)]" : "text-[color:var(--text-tertiary)]"}`}>
          <Icon name="user" className="h-5 w-5" />
          Profilo
          {isAdmin ? <span className="absolute right-4 top-2 h-1.5 w-1.5 rounded-full bg-[color:var(--danger)]" /> : null}
        </button>
      </div>
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [section, setSection] = useState<Section>(sectionFromPath(pathname));
  const [panelOpen, setPanelOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [userName, setUserName] = useState("AURA User");
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    setIsOnline(window.navigator.onLine);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  useEffect(() => {
    setSection(sectionFromPath(pathname));
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => {
        if (cancelled) return;
        const roles = new Set(me.identity.roles ?? []);
        setIsAdmin(roles.has("admin") || roles.has("tenant_admin"));
        setUserName(me.identity.display_name ?? me.identity.email ?? "AURA User");
      })
      .catch(() => {
        if (!cancelled) {
          setIsAdmin(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (isPublicPath(pathname)) {
    return <>{children}</>;
  }

  const mainLeftOffset = isMobile ? "0" : panelOpen ? "284px" : "44px";

  return (
    <div className="min-h-screen bg-[color:var(--bg-base)] text-[color:var(--text-primary)]">
      {!isOnline ? (
        <div className="fixed inset-x-0 top-0 z-[100] flex items-center justify-center gap-2 border-b border-[color:var(--warning)]/30 bg-[color:var(--warning)]/15 px-4 py-2 text-sm text-[color:var(--text-primary)]">
          <Icon name="alert-circle" className="h-4 w-4 text-[color:var(--warning)]" />
          Connessione assente - alcune funzionalita non sono disponibili
        </div>
      ) : null}

      <div className="fixed left-0 top-0 z-40 flex h-full w-[44px] flex-col border-r border-[color:var(--border)] bg-[color:var(--surface-1)]/95 backdrop-blur-xl">
        <div className="flex h-[44px] items-center justify-center border-b border-[color:var(--border)]">
          <Link href="/chat" className="flex h-7 w-7 items-center justify-center rounded-xl brand-gradient text-white" aria-label="AURA">
            <Icon name="logo" className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="flex flex-1 flex-col items-center gap-2 px-1 py-2">
          <RailItem active={section === "chat"} label="Chat" href="/chat" icon={<Icon name="message-square" className="h-4 w-4" />} />
          <RailItem active={section === "projects"} label="Progetti" onClick={() => setSection("projects")} icon={<Icon name="folder-open" className="h-4 w-4" />} />
          <RailItem active={section === "spaces"} label="Spaces" onClick={() => setSection("spaces")} icon={<Icon name="database" className="h-4 w-4" />} />
          <RailItem active={section === "agents"} label="Agents" onClick={() => setSection("agents")} icon={<Icon name="bot" className="h-4 w-4" />} />
          {isAdmin ? <RailItem active={section === "admin"} label="Admin" href="/admin/overview" icon={<Icon name="shield" className="h-4 w-4" />} visible /> : null}
          <div className="mt-auto flex flex-col items-center gap-2 pb-2">
            <button
              type="button"
              onClick={() => setPanelOpen((value) => !value)}
              className="group flex h-10 w-10 items-center justify-center rounded-xl text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
              aria-label="Toggle panel"
            >
              <Icon name="sliders" className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => router.push("/settings/profile")}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-2)] text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-hover)]"
              aria-label="Profile"
              title={userName}
            >
              <Avatar label={userName} size={28} />
            </button>
          </div>
        </div>
      </div>

      {!isMobile ? (
        <SectionPanel
          section={section}
          onOpenProfile={() => router.push("/settings/profile")}
          isAdmin={isAdmin}
          mobileOpen={panelOpen}
          onClose={() => setPanelOpen(false)}
        />
      ) : null}

      {isMobile && panelOpen ? (
        <div className="fixed inset-0 z-30 bg-[color:var(--bg-overlay)] md:hidden" onClick={() => setPanelOpen(false)}>
          <div className="absolute inset-x-0 bottom-0 rounded-t-[24px] border-t border-[color:var(--border)] bg-[color:var(--surface-1)] p-4 shadow-[var(--shadow-lg)] animate-slide-up" onClick={(event) => event.stopPropagation()}>
            <div className="mx-auto mb-3 h-1.5 w-12 rounded-full bg-[color:var(--border)]" />
            <div className="max-h-[72vh] overflow-y-auto">
              <SectionPanel
                section={section}
                onOpenProfile={() => router.push("/settings/profile")}
                isAdmin={isAdmin}
                mobileOpen
                onClose={() => setPanelOpen(false)}
                embedded
              />
            </div>
          </div>
        </div>
      ) : null}

      <div
        className="min-h-screen"
        style={{
          paddingLeft: mainLeftOffset,
          paddingBottom: isMobile ? "calc(env(safe-area-inset-bottom) + 68px)" : 0,
        }}
      >
        {children}
      </div>

      <BottomTabBar
        isAdmin={isAdmin}
        onOpenPanel={(next) => {
          setSection(next);
          setPanelOpen(true);
        }}
        onOpenProfile={() => router.push("/settings/profile")}
      />
    </div>
  );
}
