"use client";

import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { getArtifactSignedUrl } from "@/lib/api";
import type { ArtifactRef } from "@/lib/types";

const URL_TTL_MS = 14 * 60 * 1000; // 14 minutes
const MAX_PDF_PREVIEW_BYTES = 5 * 1024 * 1024;

interface SignedUrlState {
  url: string;
  fetchedAt: number;
}

function formatArtifactDate(createdAt: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(createdAt));
}

function useFreshSignedUrl(artifactId: string) {
  const [state, setState] = useState<SignedUrlState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUrl = useCallback(async () => {
    try {
      setLoading(true);
      const { url } = await getArtifactSignedUrl(artifactId);
      setState({ url, fetchedAt: Date.now() });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load artifact");
    } finally {
      setLoading(false);
    }
  }, [artifactId]);

  useEffect(() => {
    // Check if we need to re-fetch
    if (!state || Date.now() - state.fetchedAt > URL_TTL_MS) {
      fetchUrl();
    }
  }, [state, fetchUrl]);

  return { url: state?.url ?? null, loading, error, refresh: fetchUrl };
}

// ─── JSON Tree ─────────────────────────────────────────────────────────────
function JsonNode({ value, depth = 0 }: { value: unknown; depth?: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);

  if (value === null) return <span style={{ color: "#ef4444" }}>null</span>;
  if (typeof value === "boolean")
    return <span style={{ color: "#f97316" }}>{String(value)}</span>;
  if (typeof value === "number")
    return <span style={{ color: "#3b82f6" }}>{value}</span>;
  if (typeof value === "string")
    return <span style={{ color: "#22c55e" }}>&quot;{value}&quot;</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span>{"[]"}</span>;
    return (
      <span>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="text-xs mr-1"
          style={{ color: "var(--accent)" }}
        >
          {collapsed ? "▶" : "▼"}
        </button>
        {collapsed ? (
          <span style={{ color: "var(--muted-foreground)" }}>
            [{value.length} items]
          </span>
        ) : (
          <span>
            {"["}
            <div className="ml-4">
              {value.map((item, i) => (
                <div key={i}>
                  <JsonNode value={item} depth={depth + 1} />
                  {i < value.length - 1 && ","}
                </div>
              ))}
            </div>
            {"]"}
          </span>
        )}
      </span>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span>{"{}"}</span>;
    return (
      <span>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="text-xs mr-1"
          style={{ color: "var(--accent)" }}
        >
          {collapsed ? "▶" : "▼"}
        </button>
        {collapsed ? (
          <span style={{ color: "var(--muted-foreground)" }}>
            {"{"}
            {entries.length} keys{"}"}
          </span>
        ) : (
          <span>
            {"{"}
            <div className="ml-4">
              {entries.map(([k, v], i) => (
                <div key={k}>
                  <span style={{ color: "var(--foreground)" }}>&quot;{k}&quot;</span>
                  <span style={{ color: "var(--muted-foreground)" }}>: </span>
                  <JsonNode value={v} depth={depth + 1} />
                  {i < entries.length - 1 && ","}
                </div>
              ))}
            </div>
            {"}"}
          </span>
        )}
      </span>
    );
  }

  return <span>{String(value)}</span>;
}

// ─── CSV Table ─────────────────────────────────────────────────────────────
function CsvTable({ content }: { content: string }) {
  const rows = content
    .trim()
    .split("\n")
    .slice(0, 501)
    .map((row) => row.split(",").map((cell) => cell.trim().replace(/^"|"$/g, "")));
  const headers = rows[0] ?? [];
  const dataRows = rows.slice(1, 501);
  const truncated = rows.length > 501;

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th
                  key={i}
                  className="px-2 py-1 text-left font-semibold"
                  style={{
                    backgroundColor: "var(--surface-raised)",
                    border: "1px solid var(--border)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dataRows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className="px-2 py-1"
                    style={{ border: "1px solid var(--border)" }}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <p className="text-xs mt-2" style={{ color: "var(--muted-foreground)" }}>
          Showing first 500 rows.
        </p>
      )}
    </div>
  );
}

// ─── Main renderer ──────────────────────────────────────────────────────────
interface Props {
  artifact: ArtifactRef;
}

export function ArtifactRenderer({ artifact }: Props) {
  const { url, loading, error, refresh } = useFreshSignedUrl(artifact.artifact_id);
  const [content, setContent] = useState<string | null>(null);
  const [fetchingContent, setFetchingContent] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pdfPreviewAllowed, setPdfPreviewAllowed] = useState<boolean>(false);

  // For text-based artifacts, fetch the content
  const needsContent = ["markdown", "code", "csv", "json"].includes(artifact.artifact_type);

  useEffect(() => {
    if (!url || !needsContent) return;
    setFetchingContent(true);
    fetch(url)
      .then((r) => r.text())
      .then(setContent)
      .catch(() => setContent(null))
      .finally(() => setFetchingContent(false));
  }, [url, needsContent]);

  useEffect(() => {
    if (!url || artifact.artifact_type !== "pdf_preview") {
      setPdfPreviewAllowed(false);
      return;
    }

    fetch(url, { method: "HEAD" })
      .then((response) => {
        const contentLength = response.headers.get("content-length");
        if (!contentLength) {
          setPdfPreviewAllowed(false);
          return;
        }
        setPdfPreviewAllowed(Number(contentLength) < MAX_PDF_PREVIEW_BYTES);
      })
      .catch(() => setPdfPreviewAllowed(false));
  }, [artifact.artifact_type, url]);

  const handleCopy = async () => {
    if (!content) return;
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-3 text-sm" style={{ color: "var(--muted-foreground)" }}>
        <span className="spinner" />
        Loading artifact...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 p-3 text-sm" style={{ color: "#ef4444" }}>
        <span>Failed to load artifact: {error}</span>
        <button onClick={refresh} className="underline text-xs">
          Retry
        </button>
      </div>
    );
  }

  const label = artifact.label ?? artifact.artifact_type;
  const createdAtLabel = formatArtifactDate(artifact.created_at);

  const wrapper = (children: React.ReactNode) => (
    <div
      className="rounded-lg overflow-hidden my-2"
      style={{ border: "1px solid var(--border)" }}
    >
      <div
        className="flex items-center justify-between px-3 py-1.5 text-xs"
        style={{
          backgroundColor: "var(--surface-raised)",
          borderBottom: "1px solid var(--border)",
          color: "var(--muted-foreground)",
        }}
      >
        <div className="flex flex-col">
          <span>{label}</span>
          <span className="text-[10px]">{createdAtLabel}</span>
        </div>
        <span className="uppercase font-mono text-[10px]">{artifact.artifact_type}</span>
      </div>
      <div className="p-3">{children}</div>
    </div>
  );

  switch (artifact.artifact_type) {
    case "markdown":
      return wrapper(
        fetchingContent ? (
          <span className="spinner" />
        ) : content ? (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        ) : null
      );

    case "code": {
      // Try to detect language from label or default to text
      const lang = artifact.label?.match(/\.(ts|js|py|go|rs|java|sh|sql|yaml|json|css|html)$/)?.[1] ?? "text";
      return wrapper(
        fetchingContent ? (
          <span className="spinner" />
        ) : content ? (
          <div className="relative">
            <div className="absolute top-2 right-2 flex items-center gap-2 z-10">
              <span
                className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                style={{ backgroundColor: "var(--surface)", color: "var(--muted-foreground)" }}
              >
                {lang}
              </span>
              <button
                onClick={handleCopy}
                className="text-xs px-2 py-0.5 rounded transition-colors"
                style={{
                  backgroundColor: "var(--surface)",
                  color: copied ? "#22c55e" : "var(--muted-foreground)",
                }}
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <SyntaxHighlighter
              language={lang}
              style={vscDarkPlus}
              customStyle={{ margin: 0, borderRadius: 6, fontSize: 12 }}
            >
              {content}
            </SyntaxHighlighter>
          </div>
        ) : null
      );
    }

    case "csv":
      return wrapper(
        fetchingContent ? (
          <span className="spinner" />
        ) : content ? (
          <CsvTable content={content} />
        ) : null
      );

    case "json":
      if (fetchingContent) {
        return wrapper(<span className="spinner" />);
      }

      if (!content) {
        return wrapper(null);
      }

      try {
        return wrapper(
          <div className="font-mono text-xs leading-relaxed">
            <JsonNode value={JSON.parse(content)} />
          </div>
        );
      } catch {
        return wrapper(
          <div className="text-xs" style={{ color: "#ef4444" }}>
            Invalid JSON artifact payload.
          </div>
        );
      }

    case "pdf_preview":
      return wrapper(
        url ? (
          <div>
            <a
              href={url}
              download
              className="inline-flex items-center gap-1 text-sm underline mb-2"
              style={{ color: "var(--accent)" }}
            >
              Download PDF
            </a>
            {pdfPreviewAllowed ? (
              <iframe
                src={url}
                className="w-full h-96 rounded"
                style={{ border: "1px solid var(--border)" }}
                title={label}
              />
            ) : (
              <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                Preview unavailable for PDFs larger than 5 MB.
              </p>
            )}
          </div>
        ) : null
      );

    case "image":
      return wrapper(
        url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={label} loading="lazy" className="max-w-full rounded" />
        ) : null
      );

    default:
      return wrapper(
        url ? (
          <a
            href={url}
            download
            className="inline-flex items-center gap-2 text-sm underline"
            style={{ color: "var(--accent)" }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            Download {label}
          </a>
        ) : null
      );
  }
}
