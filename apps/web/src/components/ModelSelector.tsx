"use client";

import { useState } from "react";

interface Props {
  models: string[];
  selected: string | null;
  defaultModel: string;
  onChange: (model: string | null) => void;
  disabled?: boolean;
}

function modelLabel(model: string): string {
  const parts = model.split("/");
  const name = parts[parts.length - 1];
  return name.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function modelProvider(model: string): string {
  return model.split("/")[0] ?? "";
}

export function ModelSelector({ models, selected, defaultModel, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const current = selected ?? defaultModel;

  if (models.length <= 1) return null;

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setOpen((o) => !o)}
        disabled={disabled}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50"
        style={{
          background: selected ? "var(--accent-subtle)" : "var(--surface-3)",
          border: `1px solid ${selected ? "var(--accent-muted)" : "var(--border-subtle)"}`,
          color: selected ? "var(--accent)" : "var(--text-tertiary)",
        }}
        title="Select model"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
          <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 0 2h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1 0-2h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2z"/>
        </svg>
        {modelLabel(current)}
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
          <div className="absolute bottom-full left-0 z-30 mb-2 w-64 overflow-hidden rounded-xl border border-border-default bg-surface-1 shadow-xl animate-scale-in">
            <div className="border-b border-border-subtle px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">Model</p>
            </div>

            {/* Default option */}
            <button
              onMouseDown={(e) => { e.preventDefault(); onChange(null); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover"
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-text-primary">Default</div>
                <div className="text-[11px] text-text-tertiary">{modelLabel(defaultModel)}</div>
              </div>
              {!selected && (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ color: "var(--accent)" }}>
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
              )}
            </button>

            {/* Other models */}
            {models.filter((m) => m !== defaultModel).map((model) => (
              <button
                key={model}
                onMouseDown={(e) => { e.preventDefault(); onChange(model); setOpen(false); }}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-surface-hover border-t border-border-subtle"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-text-primary">{modelLabel(model)}</div>
                  <div className="text-[11px] text-text-tertiary">{modelProvider(model)}</div>
                </div>
                {selected === model && (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ color: "var(--accent)" }}>
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
