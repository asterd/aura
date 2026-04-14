"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAdminAgents, publishAgent, uploadAgent } from "@/lib/api";
import type { AgentVersion } from "@/lib/types";

type UploadState = "idle" | "uploading" | "done" | "error";

const STATUS_COLORS: Record<string, string> = {
  draft: "rgba(234,179,8,0.15)",
  published: "rgba(34,197,94,0.15)",
  archived: "rgba(156,163,175,0.15)",
};

const STATUS_TEXT: Record<string, string> = {
  draft: "#ca8a04",
  published: "#16a34a",
  archived: "#6b7280",
};

export function AgentAdminPanel() {
  const [agents, setAgents] = useState<AgentVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [manifestText, setManifestText] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminAgents();
      setAgents(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handlePublish = async (id: string) => {
    setPublishingId(id);
    try {
      const updated = await publishAgent(id);
      setAgents((prev) =>
        prev.map((a) => (a.id === id ? { ...a, status: updated.status } : a))
      );
    } catch (e) {
      alert(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishingId(null);
    }
  };

  const handleUpload = async () => {
    if (!manifestText.trim()) {
      setUploadError("Manifest YAML is required.");
      return;
    }
    if (!zipFile) {
      setUploadError("ZIP artifact is required.");
      return;
    }
    setUploadState("uploading");
    setUploadError(null);
    setUploadProgress(0);
    try {
      const result = await uploadAgent(manifestText, zipFile, ({ loaded, total }) => {
        setUploadProgress(Math.round((loaded / total) * 100));
      });
      setUploadState("done");
      setManifestText("");
      setZipFile(null);
      if (fileRef.current) fileRef.current.value = "";
      setAgents((prev) => [result, ...prev]);
    } catch (e) {
      setUploadState("error");
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    }
  };

  return (
    <div className="space-y-6">
      {/* Upload section */}
      <section
        className="rounded-2xl p-6 space-y-4"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div>
          <h3 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
            Upload Agent
          </h3>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted-foreground)" }}>
            Upload a ZIP artifact with manifest YAML. The agent will be created in draft status.
          </p>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted-foreground)" }}>
              Manifest YAML
            </label>
            <textarea
              value={manifestText}
              onChange={(e) => setManifestText(e.target.value)}
              placeholder={"name: my-agent\nversion: 1.0.0\nentrypoint: agent:build\nagent_type: pydantic_ai\ndescription: My agent"}
              rows={6}
              className="w-full rounded-xl px-3 py-2 text-sm font-mono resize-none outline-none"
              style={{
                backgroundColor: "var(--surface-raised)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted-foreground)" }}>
              ZIP Artifact
            </label>
            <input
              ref={fileRef}
              type="file"
              accept=".zip"
              onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm"
              style={{ color: "var(--foreground)" }}
            />
          </div>

          {uploadError && (
            <p className="text-sm" style={{ color: "#ef4444" }}>{uploadError}</p>
          )}

          {uploadState === "uploading" && (
            <div className="flex items-center gap-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
              <div className="w-full rounded-full h-1.5" style={{ backgroundColor: "var(--surface-raised)" }}>
                <div
                  className="h-1.5 rounded-full transition-all"
                  style={{ width: `${uploadProgress}%`, backgroundColor: "var(--accent)" }}
                />
              </div>
              <span className="flex-shrink-0">{uploadProgress}%</span>
            </div>
          )}

          {uploadState === "done" && (
            <p className="text-sm" style={{ color: "#16a34a" }}>
              Agent uploaded successfully. It is now in draft — click Publish to activate it.
            </p>
          )}

          <button
            onClick={() => void handleUpload()}
            disabled={uploadState === "uploading"}
            className="px-4 py-2 rounded-xl text-sm font-medium transition-opacity"
            style={{
              backgroundColor: "var(--accent)",
              color: "var(--accent-foreground)",
              opacity: uploadState === "uploading" ? 0.5 : 1,
            }}
          >
            {uploadState === "uploading" ? "Uploading…" : "Upload Agent"}
          </button>
        </div>
      </section>

      {/* Agent list */}
      <section
        className="rounded-2xl p-6 space-y-4"
        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>
            Agent Registry
          </h3>
          <button
            onClick={() => void load()}
            className="text-xs px-3 py-1.5 rounded-lg"
            style={{ backgroundColor: "var(--surface-raised)", color: "var(--muted-foreground)", border: "1px solid var(--border)" }}
          >
            Refresh
          </button>
        </div>

        {loading && (
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>Loading…</p>
        )}
        {error && (
          <p className="text-sm" style={{ color: "#ef4444" }}>{error}</p>
        )}
        {!loading && !error && agents.length === 0 && (
          <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
            No agents uploaded yet.
          </p>
        )}

        <div className="space-y-2">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="flex items-center gap-3 rounded-xl px-4 py-3"
              style={{ backgroundColor: "var(--surface-raised)", border: "1px solid var(--border)" }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate" style={{ color: "var(--foreground)" }}>
                    {agent.name}
                  </span>
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    v{agent.version}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span
                    className="text-xs px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: STATUS_COLORS[agent.status] ?? "transparent",
                      color: STATUS_TEXT[agent.status] ?? "var(--muted-foreground)",
                    }}
                  >
                    {agent.status}
                  </span>
                  <span className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {agent.agent_type} · {agent.entrypoint}
                  </span>
                </div>
              </div>

              {agent.status === "draft" && (
                <button
                  onClick={() => void handlePublish(agent.id)}
                  disabled={publishingId === agent.id}
                  className="flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity"
                  style={{
                    backgroundColor: "var(--accent)",
                    color: "var(--accent-foreground)",
                    opacity: publishingId === agent.id ? 0.5 : 1,
                  }}
                >
                  {publishingId === agent.id ? "Publishing…" : "Publish"}
                </button>
              )}
              {agent.status === "published" && (
                <span className="flex-shrink-0 text-xs px-3 py-1.5 rounded-lg"
                  style={{ backgroundColor: "rgba(34,197,94,0.1)", color: "#16a34a" }}>
                  Live
                </span>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
