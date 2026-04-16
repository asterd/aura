"use client";

interface Props {
  agentName: string;
}

export function AgentIndicator({ agentName }: Props) {
  return (
    <div
      className="inline-flex items-center gap-2.5 rounded-xl border px-3 py-2 text-xs agent-pulse"
      style={{
        background: "var(--accent-subtle)",
        borderColor: "var(--accent-muted)",
        color: "var(--accent)",
      }}
    >
      <div className="spinner spinner-sm" style={{ borderColor: "var(--accent-muted)", borderTopColor: "var(--accent)" }} />
      <span className="font-medium">
        Running <span className="font-semibold">{agentName}</span>…
      </span>
    </div>
  );
}
