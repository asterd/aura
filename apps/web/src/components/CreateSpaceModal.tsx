"use client";

import { useState } from "react";
import { useAuraStore } from "@/lib/store";

const BASE = "/api/v1";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (spaceId: string) => void;
}

interface SpaceApiResponse {
  id: string;
  name: string;
  slug: string;
}

async function createSpace(data: { name: string; description: string }): Promise<SpaceApiResponse> {
  const slug = data.name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
  const res = await fetch(`${BASE}/spaces`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: data.name, slug, space_type: "team", visibility: "private", source_access_mode: "space_acl_only" }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json() as Promise<SpaceApiResponse>;
}

export function CreateSpaceModal({ open, onClose, onCreated }: Props) {
  const { setAvailableSpaces, availableSpaces } = useAuraStore();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async () => {
    if (!name.trim()) { setError("Name is required."); return; }
    setSaving(true);
    setError(null);
    try {
      const space = await createSpace({ name: name.trim(), description: description.trim() });
      setAvailableSpaces([...availableSpaces, { id: space.id, name: space.name, slug: space.slug }]);
      onCreated(space.id);
      onClose();
      setName("");
      setDescription("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Creation failed");
    } finally {
      setSaving(false);
    }
  };

  const slug = name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center" style={{ background: "var(--bg-overlay)" }}>
      {/* Click outside */}
      <div className="absolute inset-0" onClick={onClose} />

      <div
        className="relative z-10 w-full max-w-md overflow-hidden rounded-2xl border border-border-subtle bg-surface-1 shadow-xl animate-slide-in-up sm:animate-scale-in"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border-subtle px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-xl"
              style={{ background: "var(--accent-subtle)", color: "var(--accent)" }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                <path d="M12 11v6M9 14h6"/>
              </svg>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-text-primary">Create Knowledge Space</h2>
              <p className="text-xs text-text-tertiary">Organize and search your documents with AI</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-text-tertiary transition-colors hover:bg-surface-hover hover:text-text-secondary"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 p-6">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-text-secondary">Space name <span className="text-danger">*</span></label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. HR Policies, Product Docs"
              className="rounded-lg border border-border-default bg-surface-2 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition-all"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter") void handleSubmit(); }}
            />
            {slug && (
              <p className="text-[11px] text-text-tertiary">
                Slug: <code className="rounded bg-surface-3 px-1 font-mono">{slug}</code>
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-text-secondary">Description <span className="text-text-tertiary">(optional)</span></label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What documents will this space contain?"
              rows={2}
              className="resize-none rounded-lg border border-border-default bg-surface-2 px-3 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 transition-all"
            />
          </div>

          <div className="rounded-xl border border-border-subtle bg-surface-2 px-3 py-3">
            <p className="text-[11px] text-text-tertiary">
              After creation, you can upload documents (PDF, Word, text) and connect sources like SharePoint or Google Drive.
            </p>
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs text-danger" style={{ background: "var(--danger-subtle)", border: "1px solid rgba(239,68,68,0.2)" }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border-subtle px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-border-default bg-surface-2 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-3"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSubmit()}
            disabled={saving || !name.trim()}
            className="rounded-lg px-4 py-2 text-sm font-semibold text-white transition-all hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-dark))" }}
          >
            {saving ? "Creating…" : "Create Space"}
          </button>
        </div>
      </div>
    </div>
  );
}
