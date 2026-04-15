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

  return (
    <div className="min-h-screen px-6 py-10" style={{ backgroundColor: "var(--background)" }}>
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Link href="/" className="text-xs uppercase tracking-[0.22em]" style={{ color: "var(--muted-foreground)" }}>
              All tenants
            </Link>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight" style={{ color: "var(--foreground)" }}>
              {tenant.display_name}
            </h1>
            <p className="mt-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
              Tenant slug: {tenant.slug}
            </p>
          </div>
          <span
            className="rounded-full px-4 py-2 text-xs font-medium uppercase tracking-[0.18em]"
            style={{
              backgroundColor: tenant.auth_mode === "local" ? "rgba(34,197,94,0.14)" : "rgba(99,102,241,0.16)",
              color: tenant.auth_mode === "local" ? "#86efac" : "#c7d2fe",
            }}
          >
            {tenant.auth_mode}
          </span>
        </div>

        {errorMessage ? (
          <div
            className="rounded-2xl px-4 py-3 text-sm"
            style={{ backgroundColor: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.35)", color: "#fecaca" }}
          >
            {errorMessage}
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-3xl border p-8" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
            {tenant.auth_mode === "local" ? (
              <>
                <h2 className="text-2xl font-semibold" style={{ color: "var(--foreground)" }}>
                  Sign in with email and password
                </h2>
                <p className="mt-2 text-sm leading-6" style={{ color: "var(--muted-foreground)" }}>
                  This tenant uses internal local authentication. Enter the credentials configured for this workspace.
                </p>

                <form action={localLogin} className="mt-8 space-y-4">
                  <input type="hidden" name="tenant_slug" value={tenant.slug} />
                  <input type="hidden" name="tenant_ref" value={tenantRef} />
                  <div>
                    <label htmlFor="email" className="block text-sm font-medium mb-1" style={{ color: "var(--foreground)" }}>
                      Email
                    </label>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      placeholder="admin@example.com"
                      className="w-full rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2"
                      style={{ backgroundColor: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                    />
                  </div>
                  <div>
                    <label htmlFor="password" className="block text-sm font-medium mb-1" style={{ color: "var(--foreground)" }}>
                      Password
                    </label>
                    <input
                      id="password"
                      name="password"
                      type="password"
                      placeholder="Workspace password"
                      className="w-full rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2"
                      style={{ backgroundColor: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full rounded-2xl px-4 py-3 text-sm font-semibold transition-opacity hover:opacity-90"
                    style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
                  >
                    Sign in
                  </button>
                </form>
              </>
            ) : (
              <>
                <h2 className="text-2xl font-semibold" style={{ color: "var(--foreground)" }}>
                  Sign in with your identity provider
                </h2>
                <p className="mt-2 text-sm leading-6" style={{ color: "var(--muted-foreground)" }}>
                  This tenant is configured for external single sign-on. Use the tenant-specific SSO entrypoint instead of
                  pasting tokens manually.
                </p>
                <div className="mt-8">
                  <Link
                    href={`/auth/oidc/start?tenant=${encodeURIComponent(tenant.slug)}`}
                    className="inline-flex w-full items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition-opacity hover:opacity-90"
                    style={{
                      backgroundColor: oidcEnabled ? "var(--accent)" : "rgba(107,114,128,0.35)",
                      color: "var(--accent-foreground)",
                      pointerEvents: oidcEnabled ? "auto" : "none",
                    }}
                  >
                    Continue with SSO
                  </Link>
                </div>
                {!oidcEnabled ? (
                  <p className="mt-4 text-sm" style={{ color: "#fca5a5" }}>
                    Set `AURA_OIDC_CLIENT_ID` in the web environment to enable the browser SSO redirect.
                  </p>
                ) : null}
              </>
            )}
          </div>

          <div className="rounded-3xl border p-8" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
            <p className="text-xs uppercase tracking-[0.22em]" style={{ color: "var(--muted-foreground)" }}>
              Tenant profile
            </p>
            <dl className="mt-6 space-y-5">
              <div>
                <dt className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--muted-foreground)" }}>
                  Authentication
                </dt>
                <dd className="mt-2 text-base font-medium" style={{ color: "var(--foreground)" }}>
                  {tenant.auth_mode === "local" ? "Local password login" : "External OIDC / Okta"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--muted-foreground)" }}>
                  Status
                </dt>
                <dd className="mt-2 text-base font-medium capitalize" style={{ color: "var(--foreground)" }}>
                  {tenant.status}
                </dd>
              </div>
              {tenant.okta_issuer ? (
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--muted-foreground)" }}>
                    Issuer
                  </dt>
                  <dd className="mt-2 break-all text-sm" style={{ color: "var(--foreground)" }}>
                    {tenant.okta_issuer}
                  </dd>
                </div>
              ) : null}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
