"use client";

interface Props {
  agentName: string;
}

export function AgentIndicator({ agentName }: Props) {
  return (
    <div
      className="flex items-center gap-2 px-4 py-2 mx-4 my-1 rounded-lg text-xs agent-pulse"
      style={{
        backgroundColor: "rgba(99,102,241,0.1)",
        border: "1px solid rgba(99,102,241,0.3)",
        color: "var(--muted-foreground)",
      }}
    >
      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} />
      <span>
        Running agent: <strong style={{ color: "var(--foreground)" }}>{agentName}</strong>
        ...
      </span>
    </div>
  );
}
