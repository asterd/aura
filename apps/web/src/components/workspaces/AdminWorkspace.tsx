"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  getAdminAgents,
  getApiKeys,
  getCurrentTenant,
  getLlmBudgets,
  getLlmCredentials,
  getLlmModels,
  getLlmProviders,
  getLlmUsage,
  getLocalUsers,
  getMe,
  getRuntimeKeyState,
} from "@/lib/api";
import type {
  ApiKeyInfo,
  CostBudget,
  LlmProvider,
  LocalAdminUser,
  MeResponse,
  RuntimeKeyState,
  TenantCredential,
  TenantModelConfig,
  TenantAdminInfo,
  UsageAggregate,
  AgentVersion,
} from "@/lib/types";
import { Badge, Button, Card, Input, PageHeader, SectionCard, Select, Skeleton, StatCard, Textarea } from "@/components/ui";
import { Icon } from "@/components/icons";

type AdminPage =
  | "overview"
  | "providers"
  | "credentials"
  | "models"
  | "budgets"
  | "users"
  | "config"
  | "branding"
  | "auth"
  | "agents"
  | "api-keys";

function adminPageFromPath(pathname: string): AdminPage {
  if (pathname.endsWith("/llm/providers")) return "providers";
  if (pathname.endsWith("/llm/credentials")) return "credentials";
  if (pathname.endsWith("/llm/models")) return "models";
  if (pathname.endsWith("/llm/budgets")) return "budgets";
  if (pathname.endsWith("/users")) return "users";
  if (pathname.endsWith("/tenant/config")) return "config";
  if (pathname.endsWith("/tenant/branding")) return "branding";
  if (pathname.endsWith("/tenant/auth")) return "auth";
  if (pathname.endsWith("/agents")) return "agents";
  if (pathname.endsWith("/api-keys")) return "api-keys";
  return "overview";
}

function AdminBreadcrumb({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-[color:var(--text-tertiary)]">
      <Link href="/chat" className="hover:text-[color:var(--text-primary)]">Chat</Link>
      <Icon name="chevron-right" className="h-3 w-3" />
      <Link href="/admin/overview" className="hover:text-[color:var(--text-primary)]">Admin</Link>
      <Icon name="chevron-right" className="h-3 w-3" />
      <span>{label}</span>
    </div>
  );
}

function Table({
  columns,
  rows,
}: {
  columns: string[];
  rows: ReactNode[][];
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-[color:var(--border)]">
      <table className="w-full text-sm">
        <thead className="bg-[color:var(--surface-2)] text-xs text-[color:var(--text-tertiary)]">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2.5 text-left font-medium">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-[color:var(--border)]">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2.5 align-top text-[color:var(--text-secondary)]">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoadingTable() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

export function AdminWorkspace() {
  const pathname = usePathname();
  const page = useMemo(() => adminPageFromPath(pathname), [pathname]);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [tenant, setTenant] = useState<TenantAdminInfo | null>(null);
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [credentials, setCredentials] = useState<TenantCredential[]>([]);
  const [models, setModels] = useState<TenantModelConfig[]>([]);
  const [budgets, setBudgets] = useState<CostBudget[]>([]);
  const [users, setUsers] = useState<LocalAdminUser[]>([]);
  const [usage, setUsage] = useState<UsageAggregate[]>([]);
  const [runtimeKey, setRuntimeKey] = useState<RuntimeKeyState | null>(null);
  const [agents, setAgents] = useState<AgentVersion[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [meRes, tenantRes, providersRes, credentialsRes, modelsRes, budgetsRes, usersRes, usageRes, runtimeKeyRes, agentsRes, apiKeysRes] = await Promise.all([
          getMe().catch(() => null),
          getCurrentTenant().catch(() => null),
          getLlmProviders().catch(() => []),
          getLlmCredentials().catch(() => []),
          getLlmModels().catch(() => []),
          getLlmBudgets().catch(() => []),
          getLocalUsers().catch(() => []),
          getLlmUsage(30).catch(() => ({ items: [] })),
          getRuntimeKeyState().catch(() => null),
          getAdminAgents().catch(() => []),
          getApiKeys().catch(() => []),
        ]);
        if (cancelled) return;
        setMe(meRes);
        setTenant(tenantRes);
        setProviders(providersRes);
        setCredentials(credentialsRes);
        setModels(modelsRes);
        setBudgets(budgetsRes);
        setUsers(usersRes);
        setUsage(usageRes.items);
        setRuntimeKey(runtimeKeyRes);
        setAgents(agentsRes);
        setApiKeys(apiKeysRes);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const statCards = useMemo(
    () => (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Utenti totali" value={String(users.length)} icon={<Icon name="users" className="h-4 w-4" />} />
        <StatCard label="Modelli attivi" value={String(models.length)} icon={<Icon name="monitor" className="h-4 w-4" />} />
        <StatCard label="Budget consumato %" value={`${Math.min(usage.reduce((sum, item) => sum + item.estimated_cost_usd, 0), 100).toFixed(0)}%`} icon={<Icon name="sliders" className="h-4 w-4" />} />
        <StatCard label="Agents pubblicati" value={String(agents.filter((agent) => agent.status === "published").length)} icon={<Icon name="bot" className="h-4 w-4" />} />
      </div>
    ),
    [agents, models.length, usage, users.length]
  );

  const content = useMemo(() => {
    switch (page) {
      case "overview":
        return (
          <div className="space-y-6">
            {loading ? <LoadingTable /> : statCards}
            <div className="grid gap-4 lg:grid-cols-2">
              <SectionCard title="Status sistemi" description="LLM, OIDC e runtime key.">
                <div className="space-y-3 text-sm">
                  <div className="flex items-center justify-between rounded-xl bg-[color:var(--surface-2)] px-3 py-2">
                    <span>Tenant</span>
                    <Badge tone={tenant?.status === "active" ? "success" : "neutral"}>{tenant?.status ?? "unknown"}</Badge>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-[color:var(--surface-2)] px-3 py-2">
                    <span>Runtime key</span>
                    <Badge tone={runtimeKey?.synced ? "success" : "warning"}>{runtimeKey?.synced ? "synced" : "pending"}</Badge>
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-[color:var(--surface-2)] px-3 py-2">
                    <span>OIDC</span>
                    <Badge tone={tenant?.auth_mode === "okta" ? "accent" : "neutral"}>{tenant?.auth_mode ?? "local"}</Badge>
                  </div>
                </div>
              </SectionCard>
              <SectionCard title="Ultimo utilizzo" description="Eventi recenti di rilievo.">
                {usage.length === 0 ? (
                  <p className="text-sm text-[color:var(--text-secondary)]">Nessun dato di utilizzo disponibile.</p>
                ) : (
                  <Table
                    columns={["Provider", "Model", "Calls", "Cost"]}
                    rows={usage.slice(0, 5).map((item) => [
                      item.provider_key,
                      item.model_name,
                      String(item.calls),
                      `$${item.estimated_cost_usd.toFixed(2)}`,
                    ])}
                  />
                )}
              </SectionCard>
            </div>
          </div>
        );
      case "providers":
        return (
          <div className="space-y-6">
            <SectionCard title="LLM Providers" description="Nome, tipo, status e base URL.">
              <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
                {loading ? (
                  <LoadingTable />
                ) : (
                  <Table
                    columns={["Nome", "Tipo", "Status", "Azioni"]}
                    rows={providers.map((provider) => [
                      provider.display_name,
                      provider.provider_key,
                      <Badge key={provider.id} tone={provider.status === "active" ? "success" : "neutral"}>{provider.status}</Badge>,
                      <div key={`${provider.id}-actions`} className="flex gap-2">
                        <Button variant="ghost" size="sm">Edit</Button>
                        <Button variant="ghost" size="sm">Delete</Button>
                      </div>,
                    ])}
                  />
                )}
                <Card className="p-4">
                  <p className="text-sm font-medium">Nuovo provider</p>
                  <div className="mt-4 space-y-3">
                    <Input placeholder="Nome" />
                    <Select defaultValue="custom">
                      <option value="openai">openai</option>
                      <option value="anthropic">anthropic</option>
                      <option value="azure">azure</option>
                      <option value="custom">custom</option>
                    </Select>
                    <Input placeholder="Base URL" />
                    <Button className="w-full">Crea provider</Button>
                  </div>
                </Card>
              </div>
            </SectionCard>
          </div>
        );
      case "credentials":
        return (
          <SectionCard title="LLM Credentials" description="Alias, provider, key mascherata e stato.">
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <Table
                columns={["Alias", "Provider", "Ultimo utilizzo", "Status", "Azioni"]}
                rows={credentials.map((credential) => [
                  credential.name,
                  credential.provider_key,
                  "n/d",
                  <Badge key={credential.id} tone={credential.status === "active" ? "success" : "danger"}>{credential.status}</Badge>,
                  <div key={`${credential.id}-actions`} className="flex gap-2">
                    <Button variant="ghost" size="sm">Edit</Button>
                    <Button variant="ghost" size="sm">Delete</Button>
                  </div>,
                ])}
              />
              <Card className="p-4">
                <p className="text-sm font-medium">Nuova credential</p>
                <div className="mt-4 space-y-3">
                  <Input placeholder="Alias" />
                  <Select defaultValue="openai">
                    <option value="openai">openai</option>
                    <option value="anthropic">anthropic</option>
                  </Select>
                  <Input placeholder="sk-..." type="password" />
                  <Textarea placeholder="Note" rows={4} />
                  <Button className="w-full">Crea credential</Button>
                </div>
              </Card>
            </div>
          </SectionCard>
        );
      case "models":
        return (
          <SectionCard title="LLM Models" description="Alias, model id, provider e policy.">
            <Table
              columns={["Alias", "Model ID", "Provider", "Policy", "Enabled", "Azioni"]}
              rows={models.map((model) => [
                model.alias ?? model.model_name,
                model.model_name,
                model.provider_key,
                model.task_type,
                <Badge key={model.id} tone={model.is_default ? "success" : "neutral"}>{model.is_default ? "on" : "off"}</Badge>,
                <div key={`${model.id}-actions`} className="flex gap-2">
                  <Button variant="ghost" size="sm">Edit</Button>
                  <Button variant="ghost" size="sm">Delete</Button>
                </div>,
              ])}
            />
          </SectionCard>
        );
      case "budgets":
        return (
          <SectionCard title="LLM Budgets" description="Scope, limiti e progresso consumi.">
            <Table
              columns={["Scope", "Limite", "Consumato", "%", "Reset", "Azioni"]}
              rows={budgets.map((budget) => {
                const consumed = Math.min((budget.soft_limit_usd ?? budget.hard_limit_usd) * 0.7, budget.hard_limit_usd);
                const percentage = Math.min(Math.round((consumed / budget.hard_limit_usd) * 100), 100);
                return [
                  budget.scope_ref,
                  `$${budget.hard_limit_usd.toFixed(2)}`,
                  `$${consumed.toFixed(2)}`,
                  <div key={budget.id} className="min-w-28">
                    <div className="h-2 overflow-hidden rounded-full bg-[color:var(--surface-3)]">
                      <div className={`h-full rounded-full ${percentage > 80 ? "bg-[color:var(--danger)]" : percentage > 60 ? "bg-[color:var(--warning)]" : "bg-[color:var(--success)]"}`} style={{ width: `${percentage}%` }} />
                    </div>
                  </div>,
                  budget.window,
                  <div key={`${budget.id}-actions`} className="flex gap-2">
                    <Button variant="ghost" size="sm">Edit</Button>
                    <Button variant="ghost" size="sm">Delete</Button>
                  </div>,
                ];
              })}
            />
          </SectionCard>
        );
      case "users":
        return (
          <SectionCard title="Utenti locali" description="Email, nome, ruolo, ultimo accesso.">
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <Table
                columns={["Email", "Nome", "Ruolo", "Creato", "Ultimo accesso", "Azioni"]}
                rows={users.map((user) => [
                  user.email,
                  user.display_name ?? "—",
                  <Badge key={user.id}>{user.roles.join(", ")}</Badge>,
                  user.created_at,
                  user.updated_at,
                  <div key={`${user.id}-actions`} className="flex gap-2">
                    <Button variant="ghost" size="sm">Role</Button>
                    <Button variant="ghost" size="sm">Reset</Button>
                    <Button variant="ghost" size="sm">Disable</Button>
                  </div>,
                ])}
              />
              <Card className="p-4">
                <p className="text-sm font-medium">Nuovo utente</p>
                <div className="mt-4 space-y-3">
                  <Input placeholder="Email" />
                  <Input placeholder="Nome" />
                  <Select defaultValue="user">
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                    <option value="tenant_admin">tenant_admin</option>
                  </Select>
                  <Input placeholder="Password temporanea" type="password" />
                  <Button className="w-full">Crea utente</Button>
                </div>
              </Card>
            </div>
          </SectionCard>
        );
      case "config":
        return (
          <SectionCard title="Tenant Config" description="Nome tenant, slug, timezone e lingua.">
            <div className="grid gap-3 md:grid-cols-2">
              <Input placeholder="Nome tenant" defaultValue={tenant?.display_name ?? ""} />
              <Input placeholder="Slug" defaultValue={tenant?.slug ?? ""} />
              <Input placeholder="Timezone" defaultValue="Europe/Rome" />
              <Input placeholder="Lingua default" defaultValue="it-IT" />
            </div>
            <div className="mt-4">
              <Button>Salva configurazione</Button>
            </div>
          </SectionCard>
        );
      case "branding":
        return (
          <SectionCard title="Tenant Branding" description="Logo, colori, nome app e preview live.">
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <div className="space-y-3">
                <Input placeholder="Logo light URL" />
                <Input placeholder="Logo dark URL" />
                <Input placeholder="Nome app" defaultValue="AURA" />
                <Input placeholder="Accent color" defaultValue="#6366f1" />
                <Button>Salva branding</Button>
              </div>
              <Card className="p-4">
                <p className="text-sm font-medium">Preview</p>
                <div className="mt-3 rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-2)] p-4">
                  <div className="flex items-center gap-3">
                    <div className="brand-gradient flex h-10 w-10 items-center justify-center rounded-2xl text-white">
                      <Icon name="logo" className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="font-semibold">{tenant?.display_name ?? "AURA"}</p>
                      <p className="text-xs text-[color:var(--text-secondary)]">Tenant applied theme</p>
                    </div>
                  </div>
                </div>
              </Card>
            </div>
          </SectionCard>
        );
      case "auth":
        return (
          <SectionCard title="Tenant Auth" description="OIDC configuration e connessione di test.">
            <div className="grid gap-3 md:grid-cols-2">
              <Input placeholder="Issuer URL" defaultValue={tenant?.okta_issuer ?? ""} />
              <Input placeholder="Client ID" />
              <Input placeholder="Client secret" type="password" />
              <Input placeholder="Scopes" defaultValue="openid profile email" />
              <Input placeholder="Redirect URI" defaultValue="/auth/oidc/callback" readOnly />
              <Select defaultValue={tenant?.auth_mode ?? "local"}>
                <option value="local">not configured</option>
                <option value="okta">configured</option>
              </Select>
            </div>
            <div className="mt-4 flex gap-3">
              <Button>Testa connessione</Button>
              <Button variant="secondary">Salva configurazione</Button>
            </div>
          </SectionCard>
        );
      case "agents":
        return (
          <SectionCard title="Agent Registry" description="Registry, versioni e stato pubblicazione.">
            <Table
              columns={["Nome", "Slug", "Versione", "Status", "Ultimo aggiornamento", "Azioni"]}
              rows={agents.map((agent) => [
                agent.name,
                agent.entrypoint,
                agent.version,
                <Badge key={agent.id} tone={agent.status === "published" ? "success" : "neutral"}>{agent.status}</Badge>,
                agent.version,
                <div key={`${agent.id}-actions`} className="flex gap-2">
                  <Button variant="ghost" size="sm">Detail</Button>
                  <Button variant="ghost" size="sm">{agent.status === "published" ? "Unpublish" : "Publish"}</Button>
                </div>,
              ])}
            />
          </SectionCard>
        );
      case "api-keys":
        return (
          <SectionCard title="Workspace API Keys" description="Chiavi workspace con reveal-once al momento della creazione.">
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <Table
                columns={["Alias", "Creata", "Ultimo utilizzo", "Scopes", "Azioni"]}
                rows={apiKeys.map((key) => [
                  key.name,
                  key.created_at,
                  key.last_used_at ?? "mai",
                  key.scopes.join(", "),
                  <div key={`${key.id}-actions`} className="flex gap-2">
                    <Button variant="ghost" size="sm">Copy</Button>
                    <Button variant="ghost" size="sm">Delete</Button>
                  </div>,
                ])}
              />
              <Card className="p-4">
                <p className="text-sm font-medium">Nuova key</p>
                <div className="mt-4 space-y-3">
                  <Input placeholder="Alias" />
                  <Textarea placeholder="Scopes separati da virgola" rows={4} />
                  <Button className="w-full">Genera key</Button>
                </div>
              </Card>
            </div>
          </SectionCard>
        );
      default:
        return null;
    }
  }, [agents, apiKeys, budgets, credentials, loading, models, page, providers, runtimeKey, statCards, tenant, usage, users]);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 md:px-6">
      <PageHeader
        title="Admin"
        description="Dashboard, LLM, tenant e workspace keys."
        action={<Button><Icon name="plus" className="h-4 w-4" />Aggiungi</Button>}
        breadcrumb={<AdminBreadcrumb label={page} />}
      />
      {content}
    </div>
  );
}
