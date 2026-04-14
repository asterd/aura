import { cookies } from "next/headers";
import { redirect } from "next/navigation";

async function storeToken(formData: FormData) {
  "use server";

  const token = formData.get("token") as string;
  if (!token?.trim()) return;

  const cookieStore = await cookies();
  cookieStore.set("aura_token", token.trim(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8, // 8 hours
  });

  redirect("/chat");
}

async function localLogin(formData: FormData) {
  "use server";

  const tenantSlug = String(formData.get("tenant_slug") || "").trim();
  const email = String(formData.get("email") || "").trim();
  const password = String(formData.get("password") || "");
  if (!tenantSlug || !email || !password) return;

  const apiBaseUrl = process.env.AURA_API_BASE_URL || "http://localhost:8000";
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/local/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_slug: tenantSlug, email, password }),
    cache: "no-store",
  });
  if (!response.ok) {
    return;
  }
  const payload = (await response.json()) as { access_token?: string };
  if (!payload.access_token) return;

  const cookieStore = await cookies();
  cookieStore.set("aura_token", payload.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });

  redirect("/chat");
}

export default async function LoginPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("aura_token");
  if (token?.value) {
    redirect("/chat");
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "var(--background)" }}>
      <div
        className="w-full max-w-md p-8 rounded-xl shadow-2xl"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight" style={{ color: "var(--foreground)" }}>
            AURA
          </h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
            AI-powered RAG + Agent platform
          </p>
        </div>

        <form action={localLogin} className="space-y-4">
          <div>
            <label htmlFor="tenant_slug" className="block text-sm font-medium mb-1" style={{ color: "var(--foreground)" }}>
              Tenant Slug
            </label>
            <input
              id="tenant_slug"
              name="tenant_slug"
              type="text"
              placeholder="example-tenant"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none focus:ring-2"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
          </div>
          <div>
            <label htmlFor="email" className="block text-sm font-medium mb-1" style={{ color: "var(--foreground)" }}>
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              placeholder="admin@example.com"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none focus:ring-2"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
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
              placeholder="Local tenant password"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none focus:ring-2"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
          </div>

          <button
            type="submit"
            className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold transition-opacity hover:opacity-90"
            style={{
              backgroundColor: "var(--accent)",
              color: "var(--accent-foreground)",
            }}
          >
            Sign in with Local Auth
          </button>
        </form>

        <div className="my-6 h-px" style={{ backgroundColor: "var(--border)" }} />

        <form action={storeToken} className="space-y-4">
          <div>
            <label
              htmlFor="token"
              className="block text-sm font-medium mb-1"
              style={{ color: "var(--foreground)" }}
            >
              JWT Token
            </label>
            <input
              id="token"
              name="token"
              type="password"
              required
              placeholder="Paste your JWT token here"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none focus:ring-2"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
          </div>

          <div
            className="flex items-start gap-2 p-3 rounded-lg text-xs"
            style={{
              backgroundColor: "rgba(99,102,241,0.1)",
              border: "1px solid rgba(99,102,241,0.3)",
              color: "var(--muted-foreground)",
            }}
          >
            <svg
              className="w-4 h-4 flex-shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
            <span>Token stored in secure httpOnly cookie only — never accessible from JavaScript.</span>
          </div>

          <button
            type="submit"
            className="w-full py-2.5 px-4 rounded-lg text-sm font-semibold transition-opacity hover:opacity-90"
            style={{
              backgroundColor: "var(--accent)",
              color: "var(--accent-foreground)",
            }}
          >
            Sign in with JWT
          </button>
        </form>

        <p className="mt-6 text-center text-xs" style={{ color: "var(--muted-foreground)" }}>
          Production tenants can use Okta. Test tenants can use internal local auth.
        </p>
      </div>
    </div>
  );
}
