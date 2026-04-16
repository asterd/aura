import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchPublicTenant, getTenantErrorMessage } from "@/lib/tenant-auth";

type TenantPageProps = {
  params: Promise<{ tenantRef: string }>;
  searchParams: Promise<{ error?: string }>;
};

async function localLogin(formData: FormData) {
  "use server";

  const tenantSlug = String(formData.get("tenant_slug") || "").trim();
  const tenantRef = String(formData.get("tenant_ref") || "").trim();
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  if (!tenantSlug || !email || !password) {
    redirect(`/tenant/${tenantRef}?error=invalid_credentials`);
  }

  const apiBaseUrl = process.env.AURA_API_BASE_URL || "http://localhost:8000";
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/local/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
    cache: "no-store",
  });
  if (!response.ok) {
    redirect(`/tenant/${tenantRef}?error=invalid_credentials`);
  }
  const payload = (await response.json()) as { access_token?: string };
  if (!payload.access_token) {
    redirect(`/tenant/${tenantRef}?error=invalid_credentials`);
  }

  const cookieStore = await cookies();
  cookieStore.set("aura_token", payload.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  cookieStore.set("aura_tenant_slug", tenantSlug, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });

  redirect("/chat");
}

export default async function TenantLoginPage({ params, searchParams }: TenantPageProps) {
  const cookieStore = await cookies();
  const token = cookieStore.get("aura_token");
  if (token?.value) {
    redirect("/chat");
  }

  const { tenantRef } = await params;
  const query = await searchParams;
  const tenant = await fetchPublicTenant(tenantRef);
  if (!tenant) {
    redirect("/?error=tenant_not_found");
  }

  const errorMessage = getTenantErrorMessage(query.error);
  const oidcEnabled = Boolean(process.env.AURA_OIDC_CLIENT_ID);
  const isOkta = tenant.auth_mode === "okta";

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-bg-base px-4 py-12">
      {/* Ambient background */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div
          className="absolute -top-32 left-1/2 h-[600px] w-[600px] -translate-x-1/2 rounded-full opacity-15 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--accent) 0%, transparent 70%)" }}
        />
      </div>

      <div className="relative z-10 flex w-full max-w-sm flex-col gap-6">
        {/* Back link */}
        <Link
          href="/"
          className="flex w-fit items-center gap-1.5 text-xs text-text-tertiary transition-colors hover:text-text-secondary"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
          All workspaces
        </Link>

        {/* Header */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-xl text-sm font-semibold"
              style={{
                background: isOkta
                  ? "linear-gradient(135deg, var(--accent-subtle), var(--accent-muted))"
                  : "linear-gradient(135deg, var(--success-subtle), rgba(34,197,94,0.2))",
                color: isOkta ? "var(--accent)" : "var(--success)",
              }}
            >
              {tenant.display_name.charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 className="text-lg font-semibold text-text-primary">{tenant.display_name}</h1>
              <p className="text-xs text-text-tertiary">{tenant.slug}</p>
            </div>
          </div>
        </div>

        {/* Error alert */}
        {errorMessage && (
          <div
            className="flex items-start gap-3 rounded-xl px-4 py-3 text-sm"
            style={{
              background: "var(--danger-subtle)",
              border: "1px solid rgba(239,68,68,0.25)",
              color: "var(--danger)",
            }}
          >
            <svg className="mt-0.5 shrink-0" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {errorMessage}
          </div>
        )}

        {/* Login card */}
        <div className="rounded-2xl border border-border-subtle bg-surface-1 p-6 shadow-md">
          {tenant.auth_mode === "local" ? (
            <form action={localLogin} className="flex flex-col gap-4">
              <input type="hidden" name="tenant_slug" value={tenant.slug} />
              <input type="hidden" name="tenant_ref" value={tenantRef} />

              <div>
                <h2 className="text-base font-semibold text-text-primary">Sign in</h2>
                <p className="mt-0.5 text-xs text-text-tertiary">
                  Use your workspace credentials
                </p>
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="email" className="text-xs font-medium text-text-secondary">
                  Email address
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  required
                  className="rounded-lg border border-border-default bg-surface-2 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition-all"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="password" className="text-xs font-medium text-text-secondary">
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                  className="rounded-lg border border-border-default bg-surface-2 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition-all"
                />
              </div>

              <button
                type="submit"
                className="mt-1 w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-all hover:opacity-90 active:scale-[0.98]"
                style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)" }}
              >
                Sign in
              </button>
            </form>
          ) : (
            <div className="flex flex-col gap-4">
              <div>
                <h2 className="text-base font-semibold text-text-primary">Single Sign-On</h2>
                <p className="mt-0.5 text-xs text-text-tertiary">
                  Sign in via your organization&apos;s identity provider
                </p>
              </div>

              {tenant.okta_issuer && (
                <div className="rounded-lg border border-border-subtle bg-surface-2 px-3 py-2.5">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary">Issuer</p>
                  <p className="mt-0.5 break-all text-xs text-text-secondary">{tenant.okta_issuer}</p>
                </div>
              )}

              <Link
                href={oidcEnabled ? `/auth/oidc/start?tenant=${encodeURIComponent(tenant.slug)}` : "#"}
                className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-all hover:opacity-90 active:scale-[0.98]"
                style={{
                  background: oidcEnabled
                    ? "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)"
                    : "var(--surface-3)",
                  color: oidcEnabled ? "white" : "var(--text-tertiary)",
                  pointerEvents: oidcEnabled ? "auto" : "none",
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                  <polyline points="10 17 15 12 10 7" />
                  <line x1="15" y1="12" x2="3" y2="12" />
                </svg>
                Continue with SSO
              </Link>

              {!oidcEnabled && (
                <p className="text-xs text-warning">
                  Set <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px]">AURA_OIDC_CLIENT_ID</code> to enable SSO.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Status indicator */}
        <div className="flex items-center justify-center gap-2">
          <div
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: tenant.status === "active" ? "var(--success)" : "var(--warning)",
            }}
          />
          <span className="text-xs capitalize text-text-tertiary">{tenant.status}</span>
        </div>
      </div>
    </div>
  );
}
