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
            Sign in
          </button>
        </form>

        <p className="mt-6 text-center text-xs" style={{ color: "var(--muted-foreground)" }}>
          In production, authentication is handled via Okta OIDC.
        </p>
      </div>
    </div>
  );
}
