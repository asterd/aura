"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getApiKeys, getMe } from "@/lib/api";
import type { ApiKeyInfo, MeResponse } from "@/lib/types";
import { Avatar, Badge, Button, Card, Input, PageHeader, SectionCard, Select, Textarea } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useTheme } from "@/app/providers";

function SettingsNavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-[color:var(--accent-subtle)] text-[color:var(--accent)]"
          : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
      }`}
    >
      <span>{label}</span>
      <Icon name="chevron-right" className="h-3.5 w-3.5" />
    </Link>
  );
}

function SettingsSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-full rounded-3xl border border-[color:var(--border)] bg-[color:var(--surface-1)] p-3 shadow-[var(--shadow-sm)] lg:w-[200px] lg:shrink-0">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
        Settings
      </p>
      <div className="space-y-1">
        <SettingsNavLink href="/settings/profile" label="Profilo" active={pathname === "/settings/profile"} />
        <SettingsNavLink href="/settings/appearance" label="Aspetto" active={pathname === "/settings/appearance"} />
        <SettingsNavLink href="/settings/api-keys" label="API Keys" active={pathname === "/settings/api-keys"} />
        <SettingsNavLink href="/settings/notifications" label="Notifiche" active={pathname === "/settings/notifications"} />
      </div>
    </aside>
  );
}

function SettingShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
      <SettingsSidebar />
      <div className="min-w-0 space-y-4">{children}</div>
    </div>
  );
}

function ThemePill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-4 py-2 text-sm transition-colors ${
        active
          ? "bg-[color:var(--accent-subtle)] text-[color:var(--accent)]"
          : "bg-[color:var(--surface-2)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]"
      }`}
    >
      {label}
    </button>
  );
}

export function SettingsWorkspace() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([]);

  useEffect(() => {
    void getMe().then(setMe).catch(() => setMe(null));
    void getApiKeys().then(setApiKeys).catch(() => setApiKeys([]));
  }, []);

  const page = useMemo(() => {
    if (pathname.endsWith("/appearance")) return "appearance";
    if (pathname.endsWith("/api-keys")) return "api-keys";
    if (pathname.endsWith("/notifications")) return "notifications";
    return "profile";
  }, [pathname]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 md:px-6">
      <PageHeader
        title="Settings"
        description="Impostazioni account, tema e chiavi personali."
        breadcrumb={
          <div className="flex items-center gap-2 text-xs text-[color:var(--text-tertiary)]">
            <Link href="/chat" className="hover:text-[color:var(--text-primary)]">Chat</Link>
            <Icon name="chevron-right" className="h-3 w-3" />
            <span>Settings</span>
          </div>
        }
      />

      <SettingShell>
        {page === "profile" ? (
          <SectionCard
            title="Profilo"
            description="Avatar, nome visualizzato e indirizzo email."
            actions={<Badge tone={me?.identity.roles.includes("admin") ? "accent" : "neutral"}>{me?.identity.roles.join(", ") || "user"}</Badge>}
          >
            <div className="grid gap-4 md:grid-cols-[auto_minmax(0,1fr)]">
              <Avatar label={me?.identity.display_name ?? me?.identity.email ?? "AURA User"} size={88} />
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <Input value={me?.identity.display_name ?? ""} readOnly placeholder="Nome visualizzato" />
                  <Input value={me?.identity.email ?? ""} readOnly placeholder="Email" />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Input placeholder="Nuova password" type="password" />
                  <Input placeholder="Conferma password" type="password" />
                </div>
                <Button>Salva profilo</Button>
              </div>
            </div>
          </SectionCard>
        ) : null}

        {page === "appearance" ? (
          <SectionCard
            title="Aspetto"
            description="Tema, densità e accent color."
          >
            <div className="space-y-6">
              <div className="flex flex-wrap gap-2">
                <ThemePill label="Light" active={theme === "light"} onClick={() => setTheme("light")} />
                <ThemePill label="Dark" active={theme === "dark"} onClick={() => setTheme("dark")} />
                <ThemePill label="System" active={theme === "system"} onClick={() => setTheme("system")} />
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {["Indigo", "Cyan", "Emerald"].map((label) => (
                  <button key={label} className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-2)] p-4 text-left transition-colors hover:bg-[color:var(--surface-hover)]">
                    <div className="h-8 w-8 rounded-full brand-gradient" />
                    <p className="mt-3 text-sm font-medium">{label}</p>
                  </button>
                ))}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Select defaultValue="comfortable">
                  <option value="comfortable">Comfortable</option>
                  <option value="compact">Compact</option>
                </Select>
                <Input placeholder="#6366f1" defaultValue="#6366f1" />
              </div>
              <Card className="p-4">
                <p className="text-sm font-medium">Preview</p>
                <p className="mt-1 text-sm text-[color:var(--text-secondary)]">
                  Tema applicato al tenant e controllabile indipendentemente dall’accent del brand.
                </p>
              </Card>
            </div>
          </SectionCard>
        ) : null}

        {page === "api-keys" ? (
          <SectionCard title="API Keys personali" description="Chiavi personali visibili una sola volta al momento della creazione.">
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <div className="overflow-hidden rounded-2xl border border-[color:var(--border)]">
                <table className="w-full text-sm">
                  <thead className="bg-[color:var(--surface-2)] text-xs text-[color:var(--text-tertiary)]">
                    <tr>
                      <th className="px-3 py-2 text-left">Alias</th>
                      <th className="px-3 py-2 text-left">Scopes</th>
                      <th className="px-3 py-2 text-left">Ultimo uso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {apiKeys.map((key) => (
                      <tr key={key.id} className="border-t border-[color:var(--border)]">
                        <td className="px-3 py-2 font-medium">{key.name}</td>
                        <td className="px-3 py-2 text-[color:var(--text-secondary)]">{key.scopes.join(", ") || "default"}</td>
                        <td className="px-3 py-2 text-[color:var(--text-secondary)]">{key.last_used_at ?? "mai"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Card className="p-4">
                <p className="text-sm font-medium">Nuova chiave</p>
                <div className="mt-3 space-y-3">
                  <Input placeholder="Alias" />
                  <Textarea rows={4} placeholder="Scopes separati da virgola" />
                  <Button className="w-full">Crea chiave</Button>
                </div>
              </Card>
            </div>
          </SectionCard>
        ) : null}

        {page === "notifications" ? (
          <SectionCard title="Notifiche" description="Browser notifications for agent completions and errors.">
            <div className="space-y-3">
              {[
                "Agent completato",
                "Errore di streaming",
                "Nuovo messaggio in thread",
              ].map((label) => (
                <div key={label} className="flex items-center justify-between rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-[color:var(--text-primary)]">{label}</p>
                    <p className="mt-1 text-xs text-[color:var(--text-secondary)]">Enable browser notifications for this event.</p>
                  </div>
                  <button className="inline-flex h-6 w-11 items-center rounded-full bg-[color:var(--surface-3)] p-1">
                    <span className="h-4 w-4 rounded-full bg-[color:var(--surface-1)] shadow-[var(--shadow-sm)]" />
                  </button>
                </div>
              ))}
            </div>
          </SectionCard>
        ) : null}
      </SettingShell>
    </div>
  );
}
