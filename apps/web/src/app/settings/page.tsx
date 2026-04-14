import { cookies } from "next/headers";
import { redirect } from "next/navigation";

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
    <div className="flex flex-col h-full items-center justify-center gap-8" style={{ backgroundColor: "var(--background)" }}>
      <div
        className="w-full max-w-md p-8 rounded-xl"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <h1 className="text-xl font-semibold mb-6" style={{ color: "var(--foreground)" }}>
          Settings
        </h1>

        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: "var(--foreground)" }}>
              Authentication
            </p>
            <p className="text-xs mb-3" style={{ color: "var(--muted-foreground)" }}>
              JWT token is stored in a secure httpOnly cookie and never accessible from JavaScript.
            </p>
            <form action={logout}>
              <button
                type="submit"
                className="px-4 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-80"
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
      </div>
    </div>
  );
}
