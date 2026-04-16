import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchPublicTenants } from "@/lib/tenant-auth";
import { PublicTenantInfo } from "@/lib/types";

export default async function RootPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("aura_token");

  if (token?.value) {
    redirect("/chat");
  }

  const tenants = await fetchPublicTenants();

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-bg-base px-4 py-12">
      {/* Ambient gradient background */}
      <div
        className="pointer-events-none absolute inset-0 overflow-hidden"
        aria-hidden="true"
      >
        <div
          className="absolute -top-40 left-1/2 h-[700px] w-[700px] -translate-x-1/2 rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--accent) 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-0 right-0 h-[400px] w-[500px] rounded-full opacity-10 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--accent-light) 0%, transparent 70%)" }}
        />
      </div>

      <div className="relative z-10 flex w-full max-w-md flex-col gap-8">
        {/* Logo / Brand */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div
            className="flex h-14 w-14 items-center justify-center rounded-2xl shadow-lg"
            style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)" }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="white"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
              Welcome to AURA
            </h1>
            <p className="mt-1 text-sm text-text-secondary">
              Select your workspace to continue
            </p>
          </div>
        </div>

        {/* Tenant cards */}
        {tenants.length === 0 ? (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center">
            <p className="text-sm text-text-secondary">No workspaces available.</p>
            <p className="mt-1 text-xs text-text-tertiary">Contact your administrator.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {tenants.map((tenant) => (
              <TenantCard key={tenant.tenant_id} tenant={tenant} />
            ))}
          </div>
        )}

        {/* Footer */}
        <p className="text-center text-xs text-text-tertiary">
          Need help?{" "}
          <a
            href="mailto:support@aura.ai"
            className="text-accent hover:text-accent-light transition-colors"
          >
            Contact support
          </a>
        </p>
      </div>
    </div>
  );
}

function TenantCard({ tenant }: { tenant: PublicTenantInfo }) {
  const isOkta = tenant.auth_mode === "okta";

  return (
    <Link
      href={`/tenant/${tenant.slug}`}
      className="group relative flex items-center gap-4 rounded-xl border border-border-subtle bg-surface-1 p-4 transition-all duration-200 hover:border-accent/40 hover:bg-surface-2 hover:shadow-md"
    >
      {/* Avatar */}
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-sm font-semibold"
        style={{
          background: isOkta
            ? "linear-gradient(135deg, var(--accent-subtle), var(--accent-muted))"
            : "linear-gradient(135deg, var(--success-subtle), rgba(34,197,94,0.2))",
          color: isOkta ? "var(--accent)" : "var(--success)",
        }}
      >
        {tenant.display_name.charAt(0).toUpperCase()}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-text-primary">
            {tenant.display_name}
          </span>
          <span
            className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{
              background: isOkta ? "var(--accent-subtle)" : "var(--success-subtle)",
              color: isOkta ? "var(--accent)" : "var(--success)",
            }}
          >
            {isOkta ? "SSO" : "Local"}
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-text-tertiary">{tenant.slug}</p>
      </div>

      {/* Chevron */}
      <svg
        className="shrink-0 text-text-tertiary transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-accent"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M9 18l6-6-6-6" />
      </svg>
    </Link>
  );
}
