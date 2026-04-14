"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createLocalUser,
  createLlmBudget,
  createLlmCredential,
  createLlmModel,
  getCurrentTenant,
  getLlmBudgets,
  getLlmCredentials,
  getLlmModels,
  getLlmProviders,
  getLlmUsage,
  getLocalUsers,
  getMe,
  provisionTenant,
  syncRuntimeKey,
  updateCurrentTenantAuth,
  updateLocalUser,
  getRuntimeKeyState,
} from "@/lib/api";
import type {
  CostBudget,
  LlmProvider,
  LocalAdminUser,
  MeResponse,
  RuntimeKeyState,
  TenantAdminInfo,
  TenantCredential,
  TenantModelConfig,
  UsageAggregate,
} from "@/lib/types";

type LoadState = "idle" | "loading" | "ready" | "error";

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-2xl p-6"
      style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <div className="mb-4">
        <h2 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
          {title}
        </h2>
        <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
          {description}
        </p>
      </div>
      {children}
    </section>
  );
}

function DataTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Array<string | number | boolean | null | undefined>>;
}) {
  return (
    <div className="overflow-x-auto rounded-xl" style={{ border: "1px solid var(--border)" }}>
      <table className="w-full text-sm">
        <thead style={{ backgroundColor: "var(--surface-raised)" }}>
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                className="px-3 py-2 text-left font-medium"
                style={{ color: "var(--foreground)" }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-4 text-center"
                style={{ color: "var(--muted-foreground)" }}
              >
                No data
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={index} style={{ borderTop: "1px solid var(--border)" }}>
                {row.map((value, cellIndex) => (
                  <td
                    key={`${index}-${cellIndex}`}
                    className="px-3 py-2 align-top"
                    style={{ color: "var(--muted-foreground)" }}
                  >
                    {String(value ?? "")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full rounded-lg px-3 py-2 text-sm outline-none focus:ring-2"
      style={{
        backgroundColor: "var(--surface-raised)",
        border: "1px solid var(--border)",
        color: "var(--foreground)",
      }}
    />
  );
}

function SelectInput(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className="w-full rounded-lg px-3 py-2 text-sm outline-none focus:ring-2"
      style={{
        backgroundColor: "var(--surface-raised)",
        border: "1px solid var(--border)",
        color: "var(--foreground)",
      }}
    />
  );
}

function ActionButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: React.ReactNode }) {
  return (
    <button
      {...props}
      className="rounded-lg px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90 disabled:opacity-50"
      style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
    >
      {children}
    </button>
  );
}

export function AdminConsole() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [tenant, setTenant] = useState<TenantAdminInfo | null>(null);
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [credentials, setCredentials] = useState<TenantCredential[]>([]);
  const [models, setModels] = useState<TenantModelConfig[]>([]);
  const [budgets, setBudgets] = useState<CostBudget[]>([]);
  const [usage, setUsage] = useState<UsageAggregate[]>([]);
  const [localUsers, setLocalUsers] = useState<LocalAdminUser[]>([]);
  const [runtimeKey, setRuntimeKey] = useState<RuntimeKeyState | null>(null);
  const [usageDays, setUsageDays] = useState("30");
  const [status, setStatus] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [tenantForm, setTenantForm] = useState({
    bootstrapToken: "",
    slug: "",
    displayName: "",
    authMode: "local",
    adminEmail: "",
    adminPassword: "",
    adminDisplayName: "",
    oktaOrgId: "",
    oktaJwksUrl: "",
    oktaIssuer: "",
    oktaAudience: "api://default",
  });

  const [tenantAuthForm, setTenantAuthForm] = useState({
    displayName: "",
    authMode: "local",
    oktaOrgId: "",
    oktaJwksUrl: "",
    oktaIssuer: "",
    oktaAudience: "api://default",
    bootstrapAdminEmail: "",
    bootstrapAdminPassword: "",
    bootstrapAdminDisplayName: "",
  });

  const [localUserForm, setLocalUserForm] = useState({
    email: "",
    displayName: "",
    password: "",
    roles: "user",
  });

  const [localUserEditForm, setLocalUserEditForm] = useState({
    userId: "",
    displayName: "",
    password: "",
    roles: "",
    isActive: true,
  });

  const [credentialForm, setCredentialForm] = useState({
    providerKey: "openai",
    name: "",
    apiKey: "",
    endpointOverride: "",
    isDefault: true,
  });

  const [modelForm, setModelForm] = useState({
    credentialId: "",
    taskType: "chat",
    modelName: "",
    alias: "",
    litellmModelName: "",
    inputCostPer1k: "",
    outputCostPer1k: "",
    rateLimitRpm: "",
    concurrencyLimit: "",
    isDefault: true,
  });

  const [budgetForm, setBudgetForm] = useState({
    scopeType: "tenant",
    scopeRef: "tenant",
    providerId: "",
    modelName: "",
    window: "monthly",
    softLimitUsd: "",
    hardLimitUsd: "",
    actionOnHardLimit: "block",
  });

  const isAdmin = useMemo(() => {
    const roles = new Set(me?.identity.roles ?? []);
    return ["admin", "tenant_admin", "platform_admin"].some((role) => roles.has(role));
  }, [me]);

  const loadAll = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const [meRes, tenantRes, providersRes, credentialsRes, modelsRes, budgetsRes, usageRes, localUsersRes, runtimeKeyRes] = await Promise.all([
        getMe(),
        getCurrentTenant().catch(() => null),
        getLlmProviders().catch(() => []),
        getLlmCredentials().catch(() => []),
        getLlmModels().catch(() => []),
        getLlmBudgets().catch(() => []),
        getLlmUsage(Number(usageDays)).catch(() => ({ items: [] })),
        getLocalUsers().catch(() => []),
        getRuntimeKeyState().catch(() => null),
      ]);
      setMe(meRes);
      setTenant(tenantRes);
      setProviders(providersRes);
      setCredentials(credentialsRes);
      setModels(modelsRes);
      setBudgets(budgetsRes);
      setUsage(usageRes.items);
      setLocalUsers(localUsersRes);
      setRuntimeKey(runtimeKeyRes);
      if (tenantRes) {
        setTenantAuthForm((current) => ({
          ...current,
          displayName: tenantRes.display_name,
          authMode: tenantRes.auth_mode,
          oktaOrgId: tenantRes.okta_org_id || "",
          oktaJwksUrl: tenantRes.okta_jwks_url || "",
          oktaIssuer: tenantRes.okta_issuer || "",
          oktaAudience: tenantRes.okta_audience || "api://default",
        }));
      }
      setStatus("ready");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Failed to load admin data.");
    }
  }, [usageDays]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  async function refreshUsage() {
    try {
      const response = await getLlmUsage(Number(usageDays));
      setUsage(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh usage.");
    }
  }

  async function refreshRuntimeKey() {
    try {
      const response = await syncRuntimeKey();
      setRuntimeKey(response);
      setNotice(`Runtime key ${response.sync_mode}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sync LiteLLM runtime key.");
    }
  }

  async function submitTenantProvision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const payload =
        tenantForm.authMode === "local"
          ? {
              slug: tenantForm.slug,
              display_name: tenantForm.displayName,
              auth_mode: tenantForm.authMode,
              admin_email: tenantForm.adminEmail,
              admin_password: tenantForm.adminPassword,
              admin_display_name: tenantForm.adminDisplayName,
            }
          : {
              slug: tenantForm.slug,
              display_name: tenantForm.displayName,
              auth_mode: tenantForm.authMode,
              okta_org_id: tenantForm.oktaOrgId || undefined,
              okta_jwks_url: tenantForm.oktaJwksUrl || undefined,
              okta_issuer: tenantForm.oktaIssuer || undefined,
              okta_audience: tenantForm.oktaAudience || undefined,
            };
      const result = await provisionTenant(payload, tenantForm.bootstrapToken);
      setNotice(`Tenant ${result.slug} created (${result.auth_mode}).`);
      setTenantForm((current) => ({
        ...current,
        slug: "",
        displayName: "",
        adminEmail: "",
        adminPassword: "",
        adminDisplayName: "",
        oktaOrgId: "",
        oktaJwksUrl: "",
        oktaIssuer: "",
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to provision tenant.");
    }
  }

  async function submitTenantAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const payload =
        tenantAuthForm.authMode === "local"
          ? {
              display_name: tenantAuthForm.displayName || undefined,
              auth_mode: tenantAuthForm.authMode,
              bootstrap_admin_email: tenantAuthForm.bootstrapAdminEmail || undefined,
              bootstrap_admin_password: tenantAuthForm.bootstrapAdminPassword || undefined,
              bootstrap_admin_display_name: tenantAuthForm.bootstrapAdminDisplayName || undefined,
            }
          : {
              display_name: tenantAuthForm.displayName || undefined,
              auth_mode: tenantAuthForm.authMode,
              okta_org_id: tenantAuthForm.oktaOrgId || undefined,
              okta_jwks_url: tenantAuthForm.oktaJwksUrl || undefined,
              okta_issuer: tenantAuthForm.oktaIssuer || undefined,
              okta_audience: tenantAuthForm.oktaAudience || undefined,
            };
      const updated = await updateCurrentTenantAuth(payload);
      setTenant(updated);
      setNotice(`Tenant auth updated to ${updated.auth_mode}.`);
      setTenantAuthForm((current) => ({
        ...current,
        displayName: updated.display_name,
        authMode: updated.auth_mode,
        oktaOrgId: updated.okta_org_id || "",
        oktaJwksUrl: updated.okta_jwks_url || "",
        oktaIssuer: updated.okta_issuer || "",
        oktaAudience: updated.okta_audience || "api://default",
        bootstrapAdminEmail: "",
        bootstrapAdminPassword: "",
        bootstrapAdminDisplayName: "",
      }));
      setLocalUsers(await getLocalUsers().catch(() => []));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update tenant auth.");
    }
  }

  async function submitCredential(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const created = await createLlmCredential({
        provider_key: credentialForm.providerKey,
        name: credentialForm.name,
        api_key: credentialForm.apiKey,
        endpoint_override: credentialForm.endpointOverride || undefined,
        is_default: credentialForm.isDefault,
      });
      setCredentials((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setCredentialForm((current) => ({ ...current, name: "", apiKey: "", endpointOverride: "" }));
      setNotice(`Credential ${created.name} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save credential.");
    }
  }

  async function submitModel(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const created = await createLlmModel({
        credential_id: modelForm.credentialId,
        task_type: modelForm.taskType,
        model_name: modelForm.modelName,
        alias: modelForm.alias || undefined,
        litellm_model_name: modelForm.litellmModelName || undefined,
        input_cost_per_1k: modelForm.inputCostPer1k ? Number(modelForm.inputCostPer1k) : undefined,
        output_cost_per_1k: modelForm.outputCostPer1k ? Number(modelForm.outputCostPer1k) : undefined,
        rate_limit_rpm: modelForm.rateLimitRpm ? Number(modelForm.rateLimitRpm) : undefined,
        concurrency_limit: modelForm.concurrencyLimit ? Number(modelForm.concurrencyLimit) : undefined,
        is_default: modelForm.isDefault,
      });
      setModels((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setModelForm((current) => ({
        ...current,
        modelName: "",
        alias: "",
        litellmModelName: "",
        inputCostPer1k: "",
        outputCostPer1k: "",
        rateLimitRpm: "",
        concurrencyLimit: "",
      }));
      setNotice(`Model ${created.model_name} enabled for ${created.task_type}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enable model.");
    }
  }

  async function submitBudget(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const created = await createLlmBudget({
        scope_type: budgetForm.scopeType,
        scope_ref: budgetForm.scopeRef,
        provider_id: budgetForm.providerId || undefined,
        model_name: budgetForm.modelName || undefined,
        window: budgetForm.window,
        soft_limit_usd: budgetForm.softLimitUsd ? Number(budgetForm.softLimitUsd) : undefined,
        hard_limit_usd: Number(budgetForm.hardLimitUsd),
        action_on_hard_limit: budgetForm.actionOnHardLimit,
      });
      setBudgets((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setBudgetForm((current) => ({ ...current, hardLimitUsd: "", softLimitUsd: "", modelName: "" }));
      setNotice(`Budget ${created.scope_type}:${created.scope_ref} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save budget.");
    }
  }

  async function submitLocalUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const created = await createLocalUser({
        email: localUserForm.email,
        password: localUserForm.password,
        display_name: localUserForm.displayName || undefined,
        roles: localUserForm.roles
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      });
      setLocalUsers((current) => [...current.filter((item) => item.id !== created.id), created].sort((a, b) => a.email.localeCompare(b.email)));
      setLocalUserForm({ email: "", displayName: "", password: "", roles: "user" });
      setNotice(`Local user ${created.email} created.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create local user.");
    }
  }

  async function submitLocalUserUpdate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    try {
      const updated = await updateLocalUser(localUserEditForm.userId, {
        display_name: localUserEditForm.displayName || undefined,
        password: localUserEditForm.password || undefined,
        roles: localUserEditForm.roles
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
        is_active: localUserEditForm.isActive,
      });
      setLocalUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)).sort((a, b) => a.email.localeCompare(b.email)));
      setLocalUserEditForm((current) => ({ ...current, password: "" }));
      setNotice(`Local user ${updated.email} updated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update local user.");
    }
  }

  useEffect(() => {
    if (!credentialForm.providerKey && providers[0]) {
      setCredentialForm((current) => ({ ...current, providerKey: providers[0].provider_key }));
    }
  }, [providers, credentialForm.providerKey]);

  useEffect(() => {
    if (localUserEditForm.userId || localUsers.length === 0) {
      return;
    }
    const firstUser = localUsers[0];
    setLocalUserEditForm({
      userId: firstUser.id,
      displayName: firstUser.display_name || "",
      password: "",
      roles: firstUser.roles.join(", "),
      isActive: firstUser.is_active,
    });
  }, [localUsers, localUserEditForm.userId]);

  if (status === "loading" || status === "idle") {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--foreground)" }}>
            Admin Console
          </h1>
          <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
            Tenant bootstrap, auth modes, LiteLLM governance, budgets and usage.
          </p>
        </div>
        <ActionButton onClick={() => void loadAll()}>Refresh</ActionButton>
      </div>

      {me && (
        <div
          className="rounded-2xl p-4 text-sm"
          style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <div style={{ color: "var(--foreground)" }}>
            Signed in as <strong>{me.identity.email}</strong>
          </div>
          <div className="mt-1" style={{ color: "var(--muted-foreground)" }}>
            Tenant: {me.identity.tenant_id} | Roles: {(me.identity.roles || []).join(", ") || "none"}
          </div>
        </div>
      )}

      {tenant && (
        <div
          className="rounded-2xl p-4 text-sm"
          style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <div style={{ color: "var(--foreground)" }}>
            Tenant <strong>{tenant.display_name}</strong> (`{tenant.slug}`)
          </div>
          <div className="mt-1" style={{ color: "var(--muted-foreground)" }}>
            Auth mode: {tenant.auth_mode} | Status: {tenant.status}
          </div>
        </div>
      )}

      {error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{ backgroundColor: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.35)", color: "#fca5a5" }}
        >
          {error}
        </div>
      )}

      {notice && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{ backgroundColor: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.35)", color: "#86efac" }}
        >
          {notice}
        </div>
      )}

      {!isAdmin ? (
        <SectionCard title="Access" description="The authenticated user does not have tenant admin privileges.">
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            Ask for role `admin`, `tenant_admin` or `platform_admin` to manage providers, budgets and tenants.
          </p>
        </SectionCard>
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard
              title="Current Tenant Auth"
              description="Switch auth mode for the current tenant and maintain bootstrap access for local auth."
            >
              <form className="space-y-3" onSubmit={(event) => void submitTenantAuth(event)}>
                <TextInput
                  placeholder="Display name"
                  value={tenantAuthForm.displayName}
                  onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, displayName: event.target.value })}
                />
                <SelectInput
                  value={tenantAuthForm.authMode}
                  onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, authMode: event.target.value })}
                >
                  <option value="local">Local</option>
                  <option value="okta">Okta</option>
                </SelectInput>
                {tenantAuthForm.authMode === "local" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextInput
                      placeholder="Bootstrap admin email"
                      value={tenantAuthForm.bootstrapAdminEmail}
                      onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, bootstrapAdminEmail: event.target.value })}
                    />
                    <TextInput
                      placeholder="Bootstrap admin display name"
                      value={tenantAuthForm.bootstrapAdminDisplayName}
                      onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, bootstrapAdminDisplayName: event.target.value })}
                    />
                    <div className="md:col-span-2">
                      <TextInput
                        type="password"
                        placeholder="Bootstrap admin password"
                        value={tenantAuthForm.bootstrapAdminPassword}
                        onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, bootstrapAdminPassword: event.target.value })}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextInput
                      placeholder="Okta org id"
                      value={tenantAuthForm.oktaOrgId}
                      onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, oktaOrgId: event.target.value })}
                    />
                    <TextInput
                      placeholder="Okta audience"
                      value={tenantAuthForm.oktaAudience}
                      onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, oktaAudience: event.target.value })}
                    />
                    <div className="md:col-span-2">
                      <TextInput
                        placeholder="Okta JWKS URL"
                        value={tenantAuthForm.oktaJwksUrl}
                        onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, oktaJwksUrl: event.target.value })}
                      />
                    </div>
                    <div className="md:col-span-2">
                      <TextInput
                        placeholder="Okta issuer"
                        value={tenantAuthForm.oktaIssuer}
                        onChange={(event) => setTenantAuthForm({ ...tenantAuthForm, oktaIssuer: event.target.value })}
                      />
                    </div>
                  </div>
                )}
                <ActionButton type="submit">Update Tenant Auth</ActionButton>
              </form>
            </SectionCard>

            <SectionCard
              title="LiteLLM Runtime Key"
              description="Tenant-scoped proxy key synced to LiteLLM where supported. Finer-grained user/provider/space gates stay enforced by AURA."
            >
              <div className="space-y-3 text-sm">
                <div style={{ color: "var(--foreground)" }}>
                  Key name: <strong>{runtimeKey?.key_name || "n/a"}</strong>
                </div>
                <div style={{ color: "var(--muted-foreground)" }}>
                  Sync mode: {runtimeKey?.sync_mode || "unknown"} | Synced: {runtimeKey?.synced ? "yes" : "no"}
                </div>
                <div style={{ color: "var(--muted-foreground)" }}>
                  Models: {runtimeKey?.models?.join(", ") || "none"}
                </div>
                <div style={{ color: "var(--muted-foreground)" }}>
                  Max budget: {runtimeKey?.max_budget_usd ?? "-"} | RPM limit: {runtimeKey?.rpm_limit ?? "-"}
                </div>
                {runtimeKey?.error ? (
                  <div style={{ color: "#fca5a5" }}>
                    Last sync error: {runtimeKey.error}
                  </div>
                ) : null}
                <ActionButton type="button" onClick={() => void refreshRuntimeKey()}>
                  Sync Runtime Key
                </ActionButton>
              </div>
            </SectionCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard
              title="Tenant Provisioning"
              description="Create local or Okta-backed tenants using the bootstrap token."
            >
              <form className="space-y-3" onSubmit={(event) => void submitTenantProvision(event)}>
                <TextInput
                  placeholder="Bootstrap token"
                  value={tenantForm.bootstrapToken}
                  onChange={(event) => setTenantForm({ ...tenantForm, bootstrapToken: event.target.value })}
                />
                <div className="grid gap-3 md:grid-cols-2">
                  <TextInput
                    placeholder="Tenant slug"
                    value={tenantForm.slug}
                    onChange={(event) => setTenantForm({ ...tenantForm, slug: event.target.value })}
                  />
                  <TextInput
                    placeholder="Display name"
                    value={tenantForm.displayName}
                    onChange={(event) => setTenantForm({ ...tenantForm, displayName: event.target.value })}
                  />
                </div>
                <SelectInput
                  value={tenantForm.authMode}
                  onChange={(event) => setTenantForm({ ...tenantForm, authMode: event.target.value })}
                >
                  <option value="local">Local</option>
                  <option value="okta">Okta</option>
                </SelectInput>
                {tenantForm.authMode === "local" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextInput
                      placeholder="Admin email"
                      value={tenantForm.adminEmail}
                      onChange={(event) => setTenantForm({ ...tenantForm, adminEmail: event.target.value })}
                    />
                    <TextInput
                      placeholder="Admin display name"
                      value={tenantForm.adminDisplayName}
                      onChange={(event) => setTenantForm({ ...tenantForm, adminDisplayName: event.target.value })}
                    />
                    <div className="md:col-span-2">
                      <TextInput
                        type="password"
                        placeholder="Admin password"
                        value={tenantForm.adminPassword}
                        onChange={(event) => setTenantForm({ ...tenantForm, adminPassword: event.target.value })}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    <TextInput
                      placeholder="Okta org id"
                      value={tenantForm.oktaOrgId}
                      onChange={(event) => setTenantForm({ ...tenantForm, oktaOrgId: event.target.value })}
                    />
                    <TextInput
                      placeholder="Okta audience"
                      value={tenantForm.oktaAudience}
                      onChange={(event) => setTenantForm({ ...tenantForm, oktaAudience: event.target.value })}
                    />
                    <div className="md:col-span-2">
                      <TextInput
                        placeholder="Okta JWKS URL"
                        value={tenantForm.oktaJwksUrl}
                        onChange={(event) => setTenantForm({ ...tenantForm, oktaJwksUrl: event.target.value })}
                      />
                    </div>
                    <div className="md:col-span-2">
                      <TextInput
                        placeholder="Okta issuer"
                        value={tenantForm.oktaIssuer}
                        onChange={(event) => setTenantForm({ ...tenantForm, oktaIssuer: event.target.value })}
                      />
                    </div>
                  </div>
                )}
                <ActionButton type="submit">Provision Tenant</ActionButton>
              </form>
            </SectionCard>

            <SectionCard
              title="Provider Credentials"
              description="Register tenant-scoped credentials and optional endpoint overrides."
            >
              <form className="space-y-3" onSubmit={(event) => void submitCredential(event)}>
                <SelectInput
                  value={credentialForm.providerKey}
                  onChange={(event) => setCredentialForm({ ...credentialForm, providerKey: event.target.value })}
                >
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.provider_key}>
                      {provider.display_name}
                    </option>
                  ))}
                </SelectInput>
                <TextInput
                  placeholder="Credential name"
                  value={credentialForm.name}
                  onChange={(event) => setCredentialForm({ ...credentialForm, name: event.target.value })}
                />
                <TextInput
                  type="password"
                  placeholder="Provider API key"
                  value={credentialForm.apiKey}
                  onChange={(event) => setCredentialForm({ ...credentialForm, apiKey: event.target.value })}
                />
                <TextInput
                  placeholder="Endpoint override (optional)"
                  value={credentialForm.endpointOverride}
                  onChange={(event) => setCredentialForm({ ...credentialForm, endpointOverride: event.target.value })}
                />
                <label className="flex items-center gap-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
                  <input
                    type="checkbox"
                    checked={credentialForm.isDefault}
                    onChange={(event) => setCredentialForm({ ...credentialForm, isDefault: event.target.checked })}
                  />
                  Mark as default provider credential
                </label>
                <ActionButton type="submit">Save Credential</ActionButton>
              </form>
            </SectionCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Enabled Models" description="Bind tenant models to credentials, task types and default selection.">
              <form className="space-y-3" onSubmit={(event) => void submitModel(event)}>
                <SelectInput
                  value={modelForm.credentialId}
                  onChange={(event) => setModelForm({ ...modelForm, credentialId: event.target.value })}
                >
                  <option value="">Select credential</option>
                  {credentials.map((credential) => (
                    <option key={credential.id} value={credential.id}>
                      {credential.provider_key} / {credential.name}
                    </option>
                  ))}
                </SelectInput>
                <div className="grid gap-3 md:grid-cols-2">
                  <SelectInput
                    value={modelForm.taskType}
                    onChange={(event) => setModelForm({ ...modelForm, taskType: event.target.value })}
                  >
                    <option value="chat">chat</option>
                    <option value="embedding">embedding</option>
                    <option value="rerank">rerank</option>
                  </SelectInput>
                  <TextInput
                    placeholder="Model name"
                    value={modelForm.modelName}
                    onChange={(event) => setModelForm({ ...modelForm, modelName: event.target.value })}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <TextInput
                    placeholder="Alias (optional)"
                    value={modelForm.alias}
                    onChange={(event) => setModelForm({ ...modelForm, alias: event.target.value })}
                  />
                  <TextInput
                    placeholder="LiteLLM runtime model"
                    value={modelForm.litellmModelName}
                    onChange={(event) => setModelForm({ ...modelForm, litellmModelName: event.target.value })}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <TextInput
                    placeholder="Input cost / 1k"
                    value={modelForm.inputCostPer1k}
                    onChange={(event) => setModelForm({ ...modelForm, inputCostPer1k: event.target.value })}
                  />
                  <TextInput
                    placeholder="Output cost / 1k"
                    value={modelForm.outputCostPer1k}
                    onChange={(event) => setModelForm({ ...modelForm, outputCostPer1k: event.target.value })}
                  />
                  <TextInput
                    placeholder="Rate limit RPM"
                    value={modelForm.rateLimitRpm}
                    onChange={(event) => setModelForm({ ...modelForm, rateLimitRpm: event.target.value })}
                  />
                  <TextInput
                    placeholder="Concurrency limit"
                    value={modelForm.concurrencyLimit}
                    onChange={(event) => setModelForm({ ...modelForm, concurrencyLimit: event.target.value })}
                  />
                </div>
                <label className="flex items-center gap-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
                  <input
                    type="checkbox"
                    checked={modelForm.isDefault}
                    onChange={(event) => setModelForm({ ...modelForm, isDefault: event.target.checked })}
                  />
                  Mark as default for task type
                </label>
                <ActionButton type="submit">Enable Model</ActionButton>
              </form>
            </SectionCard>

            <SectionCard title="Budget Gates" description="Enforce spend limits by tenant, user, provider or space.">
              <form className="space-y-3" onSubmit={(event) => void submitBudget(event)}>
                <div className="grid gap-3 md:grid-cols-2">
                  <SelectInput
                    value={budgetForm.scopeType}
                    onChange={(event) => setBudgetForm({ ...budgetForm, scopeType: event.target.value })}
                  >
                    <option value="tenant">tenant</option>
                    <option value="user">user</option>
                    <option value="provider">provider</option>
                    <option value="space">space</option>
                  </SelectInput>
                  <TextInput
                    placeholder="Scope ref"
                    value={budgetForm.scopeRef}
                    onChange={(event) => setBudgetForm({ ...budgetForm, scopeRef: event.target.value })}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <SelectInput
                    value={budgetForm.providerId}
                    onChange={(event) => setBudgetForm({ ...budgetForm, providerId: event.target.value })}
                  >
                    <option value="">Any provider</option>
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.display_name}
                      </option>
                    ))}
                  </SelectInput>
                  <TextInput
                    placeholder="Model filter (optional)"
                    value={budgetForm.modelName}
                    onChange={(event) => setBudgetForm({ ...budgetForm, modelName: event.target.value })}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <SelectInput
                    value={budgetForm.window}
                    onChange={(event) => setBudgetForm({ ...budgetForm, window: event.target.value })}
                  >
                    <option value="daily">daily</option>
                    <option value="monthly">monthly</option>
                  </SelectInput>
                  <SelectInput
                    value={budgetForm.actionOnHardLimit}
                    onChange={(event) => setBudgetForm({ ...budgetForm, actionOnHardLimit: event.target.value })}
                  >
                    <option value="block">block</option>
                    <option value="warn_only">warn_only</option>
                  </SelectInput>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <TextInput
                    placeholder="Soft limit USD"
                    value={budgetForm.softLimitUsd}
                    onChange={(event) => setBudgetForm({ ...budgetForm, softLimitUsd: event.target.value })}
                  />
                  <TextInput
                    placeholder="Hard limit USD"
                    value={budgetForm.hardLimitUsd}
                    onChange={(event) => setBudgetForm({ ...budgetForm, hardLimitUsd: event.target.value })}
                  />
                </div>
                <ActionButton type="submit">Save Budget</ActionButton>
              </form>
            </SectionCard>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard
              title="Local Users"
              description="Manage internal users for local-auth tenants. This remains empty for Okta-backed tenants."
            >
              <form className="space-y-3" onSubmit={(event) => void submitLocalUser(event)}>
                <TextInput
                  placeholder="Email"
                  value={localUserForm.email}
                  onChange={(event) => setLocalUserForm({ ...localUserForm, email: event.target.value })}
                />
                <TextInput
                  placeholder="Display name"
                  value={localUserForm.displayName}
                  onChange={(event) => setLocalUserForm({ ...localUserForm, displayName: event.target.value })}
                />
                <TextInput
                  type="password"
                  placeholder="Password"
                  value={localUserForm.password}
                  onChange={(event) => setLocalUserForm({ ...localUserForm, password: event.target.value })}
                />
                <TextInput
                  placeholder="Roles (comma separated)"
                  value={localUserForm.roles}
                  onChange={(event) => setLocalUserForm({ ...localUserForm, roles: event.target.value })}
                />
                <ActionButton type="submit">Create Local User</ActionButton>
              </form>
            </SectionCard>

            <SectionCard
              title="Update Local User"
              description="Reset password, roles or activation state for an existing local user."
            >
              <form className="space-y-3" onSubmit={(event) => void submitLocalUserUpdate(event)}>
                <SelectInput
                  value={localUserEditForm.userId}
                  onChange={(event) => {
                    const selected = localUsers.find((item) => item.id === event.target.value);
                    setLocalUserEditForm({
                      userId: event.target.value,
                      displayName: selected?.display_name || "",
                      password: "",
                      roles: selected?.roles.join(", ") || "",
                      isActive: selected?.is_active ?? true,
                    });
                  }}
                >
                  <option value="">Select local user</option>
                  {localUsers.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.email}
                    </option>
                  ))}
                </SelectInput>
                <TextInput
                  placeholder="Display name"
                  value={localUserEditForm.displayName}
                  onChange={(event) => setLocalUserEditForm({ ...localUserEditForm, displayName: event.target.value })}
                />
                <TextInput
                  type="password"
                  placeholder="New password (optional)"
                  value={localUserEditForm.password}
                  onChange={(event) => setLocalUserEditForm({ ...localUserEditForm, password: event.target.value })}
                />
                <TextInput
                  placeholder="Roles (comma separated)"
                  value={localUserEditForm.roles}
                  onChange={(event) => setLocalUserEditForm({ ...localUserEditForm, roles: event.target.value })}
                />
                <label className="flex items-center gap-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
                  <input
                    type="checkbox"
                    checked={localUserEditForm.isActive}
                    onChange={(event) => setLocalUserEditForm({ ...localUserEditForm, isActive: event.target.checked })}
                  />
                  User is active
                </label>
                <ActionButton type="submit" disabled={!localUserEditForm.userId}>
                  Update Local User
                </ActionButton>
              </form>
            </SectionCard>
          </div>

          <SectionCard title="Supported Providers" description="Catalog exposed to tenant admins.">
            <DataTable
              columns={["Provider", "Key", "Capabilities", "Base URL", "Status"]}
              rows={providers.map((provider) => [
                provider.display_name,
                provider.provider_key,
                [
                  provider.supports_chat ? "chat" : null,
                  provider.supports_embeddings ? "embed" : null,
                  provider.supports_reasoning ? "reasoning" : null,
                  provider.supports_tools ? "tools" : null,
                ]
                  .filter(Boolean)
                  .join(", "),
                provider.base_url_hint || "-",
                provider.status,
              ])}
            />
          </SectionCard>

          <SectionCard title="Local User Directory" description="Current local-auth identities registered for this tenant.">
            <DataTable
              columns={["Email", "Display Name", "Roles", "Active", "Updated"]}
              rows={localUsers.map((user) => [
                user.email,
                user.display_name || "-",
                user.roles.join(", "),
                user.is_active ? "yes" : "no",
                user.updated_at,
              ])}
            />
          </SectionCard>

          <SectionCard title="Current Credentials" description="Tenant-level provider credentials currently registered.">
            <DataTable
              columns={["Provider", "Name", "Secret Ref", "Endpoint", "Default", "Status"]}
              rows={credentials.map((credential) => [
                credential.provider_key,
                credential.name,
                credential.secret_ref,
                credential.endpoint_override || "-",
                credential.is_default ? "yes" : "no",
                credential.status,
              ])}
            />
          </SectionCard>

          <SectionCard title="Current Model Enablement" description="Allowed models per task type for this tenant.">
            <DataTable
              columns={["Task", "Provider", "Credential", "Model", "Runtime", "Cost In", "Cost Out", "Default"]}
              rows={models.map((model) => [
                model.task_type,
                model.provider_key,
                model.credential_name,
                model.alias || model.model_name,
                model.litellm_model_name || model.model_name,
                model.input_cost_per_1k ?? "-",
                model.output_cost_per_1k ?? "-",
                model.is_default ? "yes" : "no",
              ])}
            />
          </SectionCard>

          <SectionCard title="Budget Registry" description="Active budget records configured for this tenant.">
            <DataTable
              columns={["Scope", "Ref", "Provider", "Model", "Window", "Soft", "Hard", "Action"]}
              rows={budgets.map((budget) => [
                budget.scope_type,
                budget.scope_ref,
                budget.provider_id || "-",
                budget.model_name || "-",
                budget.window,
                budget.soft_limit_usd ?? "-",
                budget.hard_limit_usd,
                budget.action_on_hard_limit,
              ])}
            />
          </SectionCard>

          <SectionCard title="Usage" description="Observed usage aggregates persisted by AURA cost accounting.">
            <div className="mb-4 flex items-center gap-3">
              <TextInput
                value={usageDays}
                onChange={(event) => setUsageDays(event.target.value)}
                placeholder="Days"
                type="number"
                min={1}
              />
              <ActionButton onClick={() => void refreshUsage()}>Refresh Usage</ActionButton>
            </div>
            <DataTable
              columns={["Provider", "Model", "Task", "User", "Space", "Calls", "Input", "Output", "Estimated USD"]}
              rows={usage.map((item) => [
                item.provider_key,
                item.model_name,
                item.task_type,
                item.user_id || "-",
                item.space_id || "-",
                item.calls,
                item.input_tokens,
                item.output_tokens,
                item.estimated_cost_usd,
              ])}
            />
          </SectionCard>
        </>
      )}
    </div>
  );
}
