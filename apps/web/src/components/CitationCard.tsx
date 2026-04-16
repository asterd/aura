"use client";

import type { Citation } from "@/lib/types";

interface Props {
  citation: Citation;
  index: number;
}

export function CitationCard({ citation, index }: Props) {
  const chip = (
    <div className="group relative inline-flex items-center">
      <span
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border-subtle bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-text-secondary transition-all hover:border-accent/40 hover:bg-surface-3 hover:text-text-primary"
      >
        <span
          className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white"
          style={{ background: "var(--accent)" }}
        >
          {index + 1}
        </span>
        <span className="max-w-[140px] truncate">{citation.title}</span>
        <span className="text-text-tertiary">{citation.source_system}</span>
      </span>

      {/* Tooltip */}
      <div
        className="pointer-events-none absolute bottom-full left-0 z-50 mb-2 w-72 rounded-xl border border-border-subtle bg-surface-1 p-3.5 opacity-0 shadow-xl transition-all group-hover:pointer-events-auto group-hover:opacity-100"
      >
        <p className="mb-1 truncate text-xs font-semibold text-text-primary">{citation.title}</p>
        <p className="mb-2 text-[11px] text-text-tertiary">
          {citation.source_system}
          {citation.source_path && ` · ${citation.source_path}`}
          {citation.page_or_section && ` · ${citation.page_or_section}`}
        </p>
        {citation.snippet && (
          <p className="line-clamp-4 text-[11px] leading-relaxed text-text-secondary">
            &ldquo;{citation.snippet}&rdquo;
          </p>
        )}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[10px] text-text-tertiary">
            Relevance: {(citation.score * 100).toFixed(0)}%
          </span>
          <div
            className="h-1 w-16 overflow-hidden rounded-full bg-border-subtle"
          >
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${Math.round(citation.score * 100)}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );

  if (citation.source_url) {
    return (
      <a href={citation.source_url} target="_blank" rel="noopener noreferrer">
        {chip}
      </a>
    );
  }

  return chip;
}
