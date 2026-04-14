"use client";

import type { Citation } from "@/lib/types";

interface Props {
  citation: Citation;
  index: number;
}

export function CitationCard({ citation, index }: Props) {
  const content = (
    <div className="group relative inline-flex items-center gap-1">
      {/* Chip */}
      <span
        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer transition-colors hover:opacity-80"
        style={{
          backgroundColor: "var(--surface-raised)",
          border: "1px solid var(--border)",
          color: "var(--foreground)",
        }}
      >
        <span
          className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold"
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
        >
          {index + 1}
        </span>
        <span className="max-w-[160px] truncate">{citation.title}</span>
        <span style={{ color: "var(--muted-foreground)" }}>{citation.source_system}</span>
        {citation.page_or_section && (
          <span style={{ color: "var(--muted-foreground)" }}>· {citation.page_or_section}</span>
        )}
      </span>

      {/* Tooltip */}
      <div
        className="absolute bottom-full left-0 mb-2 w-72 p-3 rounded-lg shadow-xl z-50 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity text-xs"
        style={{
          backgroundColor: "var(--surface-raised)",
          border: "1px solid var(--border)",
          color: "var(--foreground)",
        }}
      >
        <p className="font-semibold mb-1 truncate">{citation.title}</p>
        <p className="mb-1" style={{ color: "var(--muted-foreground)" }}>
          {citation.source_system} · {citation.source_path}
          {citation.page_or_section && ` · ${citation.page_or_section}`}
        </p>
        <p className="line-clamp-4 leading-relaxed" style={{ color: "var(--foreground)" }}>
          {citation.snippet}
        </p>
        <p className="mt-1" style={{ color: "var(--muted-foreground)" }}>
          Score: {(citation.score * 100).toFixed(0)}%
        </p>
      </div>
    </div>
  );

  if (citation.source_url) {
    return (
      <a
        href={citation.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="no-underline"
      >
        {content}
      </a>
    );
  }

  return content;
}
