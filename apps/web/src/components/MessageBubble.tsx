"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { CitationCard } from "./CitationCard";
import { AgentIndicator } from "./AgentIndicator";
import { ArtifactRenderer } from "./ArtifactRenderer";
import type { Message } from "@/lib/types";

interface Props {
  message: Message;
}

const DEBOUNCE_MS = 50;

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const [displayContent, setDisplayContent] = useState(message.content);
  const pendingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce content updates during streaming
  useEffect(() => {
    if (message.status !== "STREAMING") {
      setDisplayContent(message.content);
      return;
    }
    if (pendingRef.current) clearTimeout(pendingRef.current);
    pendingRef.current = setTimeout(() => {
      setDisplayContent(message.content);
    }, DEBOUNCE_MS);
    return () => {
      if (pendingRef.current) clearTimeout(pendingRef.current);
    };
  }, [message.content, message.status]);

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-2">
        <div
          className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
          style={{
            backgroundColor: "var(--accent)",
            color: "var(--accent-foreground)",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex flex-col px-4 py-2">
      <div className="flex items-start gap-3 max-w-[85%]">
        {/* Avatar */}
        <div
          className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
        >
          A
        </div>

        <div className="flex-1 min-w-0">
          {/* Agent running indicator */}
          {message.agent_running && (
            <AgentIndicator agentName={message.agent_running.agent_name} />
          )}

          {/* Content */}
          <div
            className="px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed"
            style={{
              backgroundColor: "var(--surface)",
              border: "1px solid var(--border)",
            }}
          >
            {message.status === "PENDING" ? (
              <div className="flex items-center gap-2" style={{ color: "var(--muted-foreground)" }}>
                <span className="spinner" />
                <span>Thinking...</span>
              </div>
            ) : (
              <>
                <div
                  className={`prose prose-invert prose-sm max-w-none ${
                    message.status === "STREAMING" ? "streaming-cursor" : ""
                  }`}
                >
                  <ReactMarkdown
                    components={{
                      code({ className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className ?? "");
                        const isBlock = !!match;
                        return isBlock ? (
                          <SyntaxHighlighter
                            language={match[1]}
                            style={vscDarkPlus}
                            customStyle={{ margin: "0.5em 0", borderRadius: 6, fontSize: 12 }}
                          >
                            {String(children).replace(/\n$/, "")}
                          </SyntaxHighlighter>
                        ) : (
                          <code
                            className={className}
                            style={{
                              backgroundColor: "var(--surface-raised)",
                              padding: "1px 4px",
                              borderRadius: 3,
                              fontSize: "0.85em",
                            }}
                            {...props}
                          >
                            {children}
                          </code>
                        );
                      },
                    }}
                  >
                    {displayContent}
                  </ReactMarkdown>
                </div>

                {/* Error banner */}
                {message.status === "ERROR" && message.error && (
                  <div
                    className="mt-2 flex items-start gap-2 p-2 rounded text-xs"
                    style={{
                      backgroundColor: "rgba(239,68,68,0.1)",
                      border: "1px solid rgba(239,68,68,0.3)",
                      color: "#ef4444",
                    }}
                  >
                    <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>{message.error}</span>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Citations */}
          {message.citations.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2 ml-1">
              {message.citations.map((c, i) => (
                <CitationCard key={c.citation_id} citation={c} index={i} />
              ))}
            </div>
          )}

          {/* Artifacts */}
          {message.artifacts.length > 0 && (
            <div className="mt-2 space-y-2">
              {message.artifacts.map((a) => (
                <ArtifactRenderer key={a.artifact_id} artifact={a} />
              ))}
            </div>
          )}

          {/* Trace ID */}
          {message.status === "DONE" && message.trace_id && (
            <p className="mt-1 ml-1 text-[10px]" style={{ color: "var(--muted-foreground)" }}>
              trace: {message.trace_id}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
