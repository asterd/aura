import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { fetchPublicTenants } from "@/lib/tenant-auth";

export default async function RootPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("aura_token");

  if (token?.value) {
    redirect("/chat");
  }

  const tenants = await fetchPublicTenants();
  const defaultTenant = tenants.find((tenant) => tenant.slug === "default") || tenants[0] || null;

  return (
    <div className="min-h-screen px-6 py-10" style={{ backgroundColor: "var(--background)" }}>
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.24em]" style={{ color: "var(--muted-foreground)" }}>
            Workspace Access
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight" style={{ color: "var(--foreground)" }}>
            Choose your tenant
          </h1>
          <p className="mt-3 text-sm leading-6" style={{ color: "var(--muted-foreground)" }}>
            The application starts from the tenant and then selects the correct authentication flow for that workspace.
          </p>
        </div>

        <div className="rounded-[28px] border p-8" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
          <form action="/tenant/select" className="space-y-4">
            <label htmlFor="tenant" className="block text-sm font-medium" style={{ color: "var(--foreground)" }}>
              Tenant
            </label>
            <select
              id="tenant"
              name="tenant"
              defaultValue={defaultTenant?.slug}
              className="w-full rounded-2xl px-4 py-4 text-sm outline-none"
              style={{ backgroundColor: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--foreground)" }}
            >
              {tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.slug}>
                  {tenant.display_name} ({tenant.auth_mode})
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="w-full rounded-2xl px-4 py-4 text-sm font-semibold transition-opacity hover:opacity-90"
              style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            >
              Continue
            </button>
          </form>

          <div className="mt-6 overflow-hidden rounded-2xl border" style={{ borderColor: "var(--border)" }}>
            {tenants.map((tenant, index) => (
              <div
                key={tenant.tenant_id}
                className="flex items-center justify-between gap-4 px-4 py-4"
                style={{
                  backgroundColor: index % 2 === 0 ? "var(--surface)" : "var(--surface-raised)",
                  borderTop: index === 0 ? "none" : "1px solid var(--border)",
                }}
              >
                <div>
                  <div className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
                    {tenant.display_name}
                  </div>
                  <div className="mt-1 text-xs uppercase tracking-[0.18em]" style={{ color: "var(--muted-foreground)" }}>
                    {tenant.slug}
                  </div>
                </div>
                <div className="text-xs font-medium uppercase tracking-[0.18em]" style={{ color: "var(--muted-foreground)" }}>
                  {tenant.auth_mode}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
