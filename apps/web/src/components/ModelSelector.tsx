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
  return name
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
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
        className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium"
        style={{
          backgroundColor: selected ? "rgba(99,102,241,0.1)" : "var(--surface-raised)",
          color: selected ? "var(--accent)" : "var(--muted-foreground)",
          border: "1px solid var(--border)",
          opacity: disabled ? 0.5 : 1,
        }}
        title="Select model"
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        {modelLabel(current)}
        <svg className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div
            className="absolute bottom-full mb-2 left-0 w-64 rounded-xl shadow-xl overflow-hidden z-30"
            style={{ backgroundColor: "var(--surface-raised)", border: "1px solid var(--border)" }}
          >
            <div className="px-3 py-2" style={{ borderBottom: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold" style={{ color: "var(--muted-foreground)" }}>MODEL</p>
            </div>

            <button
              onMouseDown={(e) => { e.preventDefault(); onChange(null); setOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-left hover:opacity-80"
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <span className="flex-1 text-sm" style={{ color: "var(--foreground)" }}>
                Default ({modelLabel(defaultModel)})
              </span>
              {!selected && (
                <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="var(--accent)" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>

            {models.filter((m) => m !== defaultModel).map((model) => (
              <button
                key={model}
                onMouseDown={(e) => { e.preventDefault(); onChange(model); setOpen(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:opacity-80"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <span className="flex-1 text-sm" style={{ color: "var(--foreground)" }}>
                  {modelLabel(model)}
                </span>
                <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  {model.split("/")[0]}
                </span>
                {selected === model && (
                  <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="var(--accent)" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
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
