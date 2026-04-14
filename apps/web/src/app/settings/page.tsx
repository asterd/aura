import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { AdminConsole } from "@/components/AdminConsole";

async function logout() {
  "use server";
  const cookieStore = await cookies();
  cookieStore.delete("aura_token");
  redirect("/login");
}

export default async function SettingsPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get("aura_token");
  if (!token?.value) redirect("/login");

  return (
    <div className="h-full overflow-y-auto" style={{ backgroundColor: "var(--background)" }}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-8">
        <div
          className="flex flex-col gap-4 rounded-2xl p-6 md:flex-row md:items-center md:justify-between"
          style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
        >
          <div>
            <h1 className="text-2xl font-semibold" style={{ color: "var(--foreground)" }}>
              Settings
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted-foreground)" }}>
              Authentication, tenant provisioning and LiteLLM governance for the current workspace.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/chat"
              className="rounded-lg px-4 py-2 text-sm font-medium transition-opacity hover:opacity-80"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            >
              Back to chat
            </Link>
            <form action={logout}>
              <button
                type="submit"
                className="rounded-lg px-4 py-2 text-sm font-medium transition-opacity hover:opacity-80"
                style={{
                  backgroundColor: "rgba(239,68,68,0.15)",
                  border: "1px solid rgba(239,68,68,0.4)",
                  color: "#ef4444",
                }}
              >
                Sign out
              </button>
            </form>
          </div>
        </div>

        <div
          className="rounded-2xl p-4 text-xs"
          style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted-foreground)" }}
        >
          JWT tokens remain stored in a secure httpOnly cookie. Local-auth tenant bootstrap requires the configured bootstrap token.
        </div>

        <AdminConsole />
      </div>
    </div>
  );
}
