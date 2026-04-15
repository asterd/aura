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

async function createSpace(data: {
  name: string;
  description: string;
}): Promise<SpaceApiResponse> {
  const slug = data.name
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
  const res = await fetch(`${BASE}/spaces`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: data.name,
      slug,
      space_type: "rag",
      visibility: "private",
      source_access_mode: "tenant_members",
    }),
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
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
    >
      <div
        className="w-full max-w-md rounded-2xl p-6 space-y-5"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
            Create Knowledge Space
          </h2>
          <button
            onClick={onClose}
            className="opacity-50 hover:opacity-100"
            style={{ color: "var(--muted-foreground)" }}
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--muted-foreground)" }}
            >
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. HR Policies, Product Docs"
              className="w-full px-3 py-2 rounded-xl text-sm outline-none"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
              autoFocus
            />
          </div>

          <div>
            <label
              className="block text-xs font-medium mb-1"
              style={{ color: "var(--muted-foreground)" }}
            >
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What documents will this space contain?"
              rows={2}
              className="w-full px-3 py-2 rounded-xl text-sm outline-none resize-none"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
          </div>

          <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
            After creation you can upload documents and connect SharePoint or other sources.
          </p>
        </div>

        {error && (
          <p className="text-sm" style={{ color: "#ef4444" }}>
            {error}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium"
            style={{
              backgroundColor: "var(--surface-raised)",
              color: "var(--muted-foreground)",
              border: "1px solid var(--border)",
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSubmit()}
            disabled={saving || !name.trim()}
            className="px-4 py-2 rounded-xl text-sm font-medium"
            style={{
              backgroundColor: "var(--accent)",
              color: "var(--accent-foreground)",
              opacity: saving || !name.trim() ? 0.5 : 1,
            }}
          >
            {saving ? "Creating…" : "Create Space"}
          </button>
        </div>
      </div>
    </div>
  );
}
