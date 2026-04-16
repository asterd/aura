"use client";

import { useState } from "react";
import type { Space } from "@/lib/types";

interface Props {
  spaces: Space[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}

export function SpaceSelector({ spaces, selectedIds, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);

  const toggle = (id: string) => {
    onChange(selectedIds.includes(id) ? selectedIds.filter((s) => s !== id) : [...selectedIds, id]);
  };

  const isFreeChatMode = selectedIds.length === 0;
  const label =
    selectedIds.length === 0
      ? "Free Chat"
      : selectedIds.length === 1
      ? (spaces.find((s) => s.id === selectedIds[0])?.name ?? "1 space")
      : `${selectedIds.length} spaces`;

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50"
        style={{
          background: isFreeChatMode ? "var(--surface-3)" : "var(--accent-subtle)",
          border: `1px solid ${isFreeChatMode ? "var(--border-subtle)" : "var(--accent-muted)"}`,
          color: isFreeChatMode ? "var(--text-tertiary)" : "var(--accent)",
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span>{label}</span>
        <svg
          className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
        >
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div
            role="listbox"
            className="absolute bottom-full left-0 z-30 mb-2 w-72 overflow-hidden rounded-xl border border-border-default bg-surface-1 shadow-xl animate-scale-in"
          >
            <div className="border-b border-border-subtle px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
                Knowledge Spaces
              </p>
            </div>

            {/* Free Chat */}
            <button
              role="option"
              aria-selected={isFreeChatMode}
              onMouseDown={(e) => { e.preventDefault(); onChange([]); setOpen(false); }}
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover"
            >
              <Checkbox checked={isFreeChatMode} />
              <div className="flex min-w-0 flex-1 items-center justify-between">
                <span className="text-sm font-medium text-text-primary">Free Chat</span>
                <span className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary">No RAG</span>
              </div>
            </button>

            {/* Spaces */}
            {spaces.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs text-text-tertiary">
                No knowledge spaces available.<br />
                Ask an admin to create one.
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto">
                {spaces.map((space) => {
                  const selected = selectedIds.includes(space.id);
                  return (
                    <button
                      key={space.id}
                      role="option"
                      aria-selected={selected}
                      onMouseDown={(e) => { e.preventDefault(); toggle(space.id); }}
                      className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover"
                    >
                      <Checkbox checked={selected} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-text-primary">{space.name}</div>
                        {space.slug && <div className="truncate text-[11px] text-text-tertiary">{space.slug}</div>}
                      </div>
                      {space.space_type && (
                        <span
                          className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase"
                          style={{ background: "var(--surface-3)", color: "var(--text-tertiary)" }}
                        >
                          {space.space_type}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="border-t border-border-subtle px-3 py-2">
              <p className="text-[10px] text-text-tertiary">
                Tip: type <code className="rounded bg-surface-3 px-1 font-mono">#space-name</code> to mention a space
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Checkbox({ checked }: { checked: boolean }) {
  return (
    <span
      className="flex h-4 w-4 shrink-0 items-center justify-center rounded"
      style={{
        border: `1.5px solid ${checked ? "var(--accent)" : "var(--border-default)"}`,
        background: checked ? "var(--accent)" : "transparent",
        transition: "all 0.1s",
      }}
    >
      {checked && (
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
      )}
    </span>
  );
}
