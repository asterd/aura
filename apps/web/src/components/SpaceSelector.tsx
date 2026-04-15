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
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((s) => s !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  };

  const label =
    selectedIds.length === 0
      ? "Free Chat"
      : selectedIds.length === 1
      ? (spaces.find((s) => s.id === selectedIds[0])?.name ?? "1 space")
      : `${selectedIds.length} spaces`;

  const isFreeChatMode = selectedIds.length === 0;

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium transition-colors"
        style={{
          backgroundColor: isFreeChatMode ? "var(--surface-raised)" : "var(--accent)",
          color: isFreeChatMode ? "var(--muted-foreground)" : "var(--accent-foreground)",
          border: "1px solid var(--border)",
          opacity: disabled ? 0.5 : 1,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
        title="Select knowledge spaces"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {/* Book/space icon */}
        <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          />
        </svg>
        <span>{label}</span>
        <svg
          className={`w-3 h-3 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <>
          {/* Click-outside overlay */}
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />

          <div
            role="listbox"
            className="absolute bottom-full mb-2 left-0 w-72 rounded-xl shadow-xl overflow-hidden z-30"
            style={{
              backgroundColor: "var(--surface-raised)",
              border: "1px solid var(--border)",
            }}
          >
            {/* Header */}
            <div className="px-3 py-2" style={{ borderBottom: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold tracking-wide" style={{ color: "var(--muted-foreground)" }}>
                KNOWLEDGE SPACES
              </p>
            </div>

            {/* Free Chat option */}
            <button
              role="option"
              aria-selected={isFreeChatMode}
              onMouseDown={(e) => {
                e.preventDefault();
                onChange([]);
                setOpen(false);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:opacity-80 transition-opacity"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <Checkbox checked={isFreeChatMode} />
              <div className="flex-1 min-w-0">
                <span className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
                  Free Chat
                </span>
              </div>
              <span className="text-xs flex-shrink-0" style={{ color: "var(--muted-foreground)" }}>
                No RAG
              </span>
            </button>

            {/* Space list */}
            {spaces.length === 0 ? (
              <div className="px-3 py-4 text-xs text-center" style={{ color: "var(--muted-foreground)" }}>
                No knowledge spaces available.
                <br />
                Ask an admin to create one.
              </div>
            ) : (
              spaces.map((space) => {
                const selected = selectedIds.includes(space.id);
                return (
                  <button
                    key={space.id}
                    role="option"
                    aria-selected={selected}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      toggle(space.id);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:opacity-80 transition-opacity"
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <Checkbox checked={selected} />
                    <div className="flex flex-col items-start min-w-0 flex-1">
                      <span className="text-sm font-medium truncate w-full" style={{ color: "var(--foreground)" }}>
                        {space.name}
                      </span>
                      {space.slug && (
                        <span className="text-xs truncate w-full" style={{ color: "var(--muted-foreground)" }}>
                          {space.slug}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })
            )}

            {/* Footer hint */}
            <div className="px-3 py-2 text-xs" style={{ color: "var(--muted-foreground)", borderTop: "1px solid var(--border)" }}>
              Tip: type <strong>#space-name</strong> in your message to mention a space
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
      className="w-4 h-4 rounded flex-shrink-0 flex items-center justify-center"
      style={{
        border: `2px solid ${checked ? "var(--accent)" : "var(--border)"}`,
        backgroundColor: checked ? "var(--accent)" : "transparent",
        transition: "background-color 0.1s, border-color 0.1s",
      }}
    >
      {checked && (
        <svg className="w-2.5 h-2.5" fill="none" stroke="var(--accent-foreground)" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
        </svg>
      )}
    </span>
  );
}
