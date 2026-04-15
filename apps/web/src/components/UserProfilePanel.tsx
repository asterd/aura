"use client";

import { useCallback, useEffect, useState } from "react";
import { getMe } from "@/lib/api";

const BASE = "/api/v1";

interface ProfileResponse {
  user_id: string;
  email: string;
  display_name: string | null;
  roles: string[];
  tenant_id: string;
}

async function updateProfile(displayName: string): Promise<ProfileResponse> {
  const res = await fetch(`${BASE}/auth/me`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<ProfileResponse>;
}

async function changePassword(current: string, next: string): Promise<void> {
  const res = await fetch(`${BASE}/auth/me/change-password`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: current, new_password: next }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

export function UserProfilePanel() {
  const [email, setEmail] = useState("");
  const [userId, setUserId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    getMe()
      .then((data) => {
        setEmail(data.identity.email);
        setUserId(data.identity.user_id);
        setTenantId(data.identity.tenant_id);
        setRoles(data.identity.roles);
        setDisplayName(data.identity.display_name ?? "");
      })
      .catch(() => {/* silent */})
      .finally(() => setLoading(false));
  }, []);

  const handleSaveProfile = useCallback(async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await updateProfile(displayName);
      setDisplayName(updated.display_name ?? "");
      setSaveMsg("Profile updated.");
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [displayName]);

  const handleChangePassword = useCallback(async () => {
    if (newPw !== confirmPw) {
      setPwMsg({ ok: false, text: "Passwords do not match." });
      return;
    }
    if (newPw.length < 8) {
      setPwMsg({ ok: false, text: "Password must be at least 8 characters." });
      return;
    }
    setPwSaving(true);
    setPwMsg(null);
    try {
      await changePassword(currentPw, newPw);
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setPwMsg({ ok: true, text: "Password changed successfully." });
    } catch (e) {
      setPwMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setPwSaving(false);
    }
  }, [currentPw, newPw, confirmPw]);

  if (loading)
    return (
      <div className="p-6 text-sm" style={{ color: "var(--muted-foreground)" }}>
        Loading…
      </div>
    );

  return (
    <div className="space-y-6">
      {/* Profile */}
      <section
        className="rounded-2xl p-6 space-y-4"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div>
          <h3 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
            Profile
          </h3>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            Your account information.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--muted-foreground)" }}
            >
              Email
            </label>
            <p
              className="text-sm px-3 py-2 rounded-xl"
              style={{ backgroundColor: "var(--surface-raised)", color: "var(--muted-foreground)" }}
            >
              {email}
            </p>
          </div>
          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--muted-foreground)" }}
            >
              Display Name
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-2 rounded-xl text-sm outline-none"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
          </div>
        </div>

        {saveMsg && (
          <p
            className="text-sm"
            style={{ color: saveMsg.includes("updated") ? "#16a34a" : "#ef4444" }}
          >
            {saveMsg}
          </p>
        )}

        <button
          onClick={() => void handleSaveProfile()}
          disabled={saving}
          className="px-4 py-2 rounded-xl text-sm font-medium"
          style={{
            backgroundColor: "var(--accent)",
            color: "var(--accent-foreground)",
            opacity: saving ? 0.5 : 1,
          }}
        >
          {saving ? "Saving…" : "Save Profile"}
        </button>
      </section>

      {/* Change password — local auth only */}
      <section
        className="rounded-2xl p-6 space-y-4"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div>
          <h3 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
            Change Password
          </h3>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            Only available for local authentication. Okta-managed accounts cannot change password
            here.
          </p>
        </div>

        <div className="space-y-3 max-w-sm">
          {(
            [
              ["Current password", currentPw, setCurrentPw],
              ["New password", newPw, setNewPw],
              ["Confirm new password", confirmPw, setConfirmPw],
            ] as [string, string, (v: string) => void][]
          ).map(([label, val, setter]) => (
            <div key={label}>
              <label
                className="block text-xs font-medium mb-1"
                style={{ color: "var(--muted-foreground)" }}
              >
                {label}
              </label>
              <input
                type="password"
                value={val}
                onChange={(e) => setter(e.target.value)}
                className="w-full px-3 py-2 rounded-xl text-sm outline-none"
                style={{
                  backgroundColor: "var(--surface-raised)",
                  border: "1px solid var(--border)",
                  color: "var(--foreground)",
                }}
              />
            </div>
          ))}
        </div>

        {pwMsg && (
          <p className="text-sm" style={{ color: pwMsg.ok ? "#16a34a" : "#ef4444" }}>
            {pwMsg.text}
          </p>
        )}

        <button
          onClick={() => void handleChangePassword()}
          disabled={pwSaving || !currentPw || !newPw || !confirmPw}
          className="px-4 py-2 rounded-xl text-sm font-medium"
          style={{
            backgroundColor: "var(--accent)",
            color: "var(--accent-foreground)",
            opacity: pwSaving || !currentPw || !newPw || !confirmPw ? 0.5 : 1,
          }}
        >
          {pwSaving ? "Changing…" : "Change Password"}
        </button>
      </section>

      {/* Account info */}
      <section
        className="rounded-2xl p-4"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex flex-wrap gap-4 text-xs" style={{ color: "var(--muted-foreground)" }}>
          <span>
            Tenant:{" "}
            <strong style={{ color: "var(--foreground)" }}>{tenantId.slice(0, 8)}…</strong>
          </span>
          <span>
            User ID:{" "}
            <strong style={{ color: "var(--foreground)" }}>{userId.slice(0, 8)}…</strong>
          </span>
          <span>
            Roles:{" "}
            <strong style={{ color: "var(--foreground)" }}>{roles.join(", ") || "user"}</strong>
          </span>
        </div>
      </section>
    </div>
  );
}
