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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-text-tertiary">{label}</label>
      {children}
    </div>
  );
}

function SectionCard({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border-subtle bg-surface-1 p-6">
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-text-tertiary">{description}</p>}
      </div>
      {children}
    </div>
  );
}

export function UserProfilePanel() {
  const [email, setEmail] = useState("");
  const [userId, setUserId] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);

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
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSaveProfile = useCallback(async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await updateProfile(displayName);
      setDisplayName(updated.display_name ?? "");
      setSaveMsg({ ok: true, text: "Profile updated." });
    } catch (e) {
      setSaveMsg({ ok: false, text: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  }, [displayName]);

  const handleChangePassword = useCallback(async () => {
    if (newPw !== confirmPw) { setPwMsg({ ok: false, text: "Passwords do not match." }); return; }
    if (newPw.length < 8) { setPwMsg({ ok: false, text: "Password must be at least 8 characters." }); return; }
    setPwSaving(true);
    setPwMsg(null);
    try {
      await changePassword(currentPw, newPw);
      setCurrentPw(""); setNewPw(""); setConfirmPw("");
      setPwMsg({ ok: true, text: "Password changed successfully." });
    } catch (e) {
      setPwMsg({ ok: false, text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setPwSaving(false);
    }
  }, [currentPw, newPw, confirmPw]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border-subtle bg-surface-1 p-6">
        <div className="flex items-center gap-3">
          <div className="skeleton h-10 w-10 rounded-xl" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-4 w-32" />
            <div className="skeleton h-3 w-48" />
          </div>
        </div>
      </div>
    );
  }

  const initials = (displayName || email).slice(0, 2).toUpperCase();

  return (
    <div className="space-y-4">
      {/* Profile header */}
      <SectionCard title="My Profile" description="Your personal information and account details.">
        <div className="flex items-start gap-4">
          {/* Avatar */}
          <div
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-sm font-semibold text-white"
            style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)" }}
          >
            {initials}
          </div>

          <div className="min-w-0 flex-1">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Field label="Email address">
                <div className="rounded-lg border border-border-subtle bg-surface-2 px-3 py-2.5 text-sm text-text-secondary">
                  {email}
                </div>
              </Field>
              <Field label="Display name">
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  className="rounded-lg border border-border-default bg-surface-2 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition-all"
                />
              </Field>
            </div>

            {saveMsg && (
              <p className={`mt-3 text-xs ${saveMsg.ok ? "text-success" : "text-danger"}`}>
                {saveMsg.ok ? "✓" : "✗"} {saveMsg.text}
              </p>
            )}

            <button
              onClick={() => void handleSaveProfile()}
              disabled={saving}
              className="mt-4 rounded-lg px-4 py-2 text-sm font-semibold text-white transition-all hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-dark))" }}
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>

        {/* Account meta */}
        <div className="mt-5 flex flex-wrap gap-3 border-t border-border-subtle pt-4">
          {[
            { label: "Tenant", value: tenantId.slice(0, 8) + "…" },
            { label: "User ID", value: userId.slice(0, 8) + "…" },
            { label: "Roles", value: roles.join(", ") || "user" },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-1.5">
              <span className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary">{label}</span>
              <span className="text-xs font-medium text-text-secondary">{value}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      {/* Change password */}
      <SectionCard
        title="Change Password"
        description="Only available for local authentication. Okta-managed accounts manage passwords through your IdP."
      >
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {([
            ["Current password", currentPw, setCurrentPw],
            ["New password", newPw, setNewPw],
            ["Confirm new password", confirmPw, setConfirmPw],
          ] as [string, string, (v: string) => void][]).map(([label, val, setter]) => (
            <Field key={label} label={label}>
              <input
                type="password"
                value={val}
                onChange={(e) => setter(e.target.value)}
                placeholder="••••••••"
                className="rounded-lg border border-border-default bg-surface-2 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition-all"
              />
            </Field>
          ))}
        </div>

        {pwMsg && (
          <p className={`mt-3 text-xs ${pwMsg.ok ? "text-success" : "text-danger"}`}>
            {pwMsg.ok ? "✓" : "✗"} {pwMsg.text}
          </p>
        )}

        <button
          onClick={() => void handleChangePassword()}
          disabled={pwSaving || !currentPw || !newPw || !confirmPw}
          className="mt-4 rounded-lg px-4 py-2 text-sm font-semibold text-white transition-all hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-dark))" }}
        >
          {pwSaving ? "Changing…" : "Change Password"}
        </button>
      </SectionCard>
    </div>
  );
}
