"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { CitationCard } from "./CitationCard";
import { ArtifactRenderer } from "./ArtifactRenderer";
import type { Message } from "@/lib/types";
import { Icon } from "./icons";

interface Props {
  message: Message;
}

const DEBOUNCE_MS = 40;

function hashHue(value: string) {
  let hash = 0;
  for (const char of value) hash = (hash << 5) - hash + char.charCodeAt(0);
  return Math.abs(hash) % 360;
}

function AvatarMark() {
  return (
    <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl brand-gradient text-white shadow-[var(--shadow-sm)]">
      <Icon name="logo" className="h-3.5 w-3.5" />
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1.5">
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="h-2 w-2 animate-pulse rounded-full bg-[color:var(--text-tertiary)]"
          style={{ animationDelay: `${index * 120}ms` }}
        />
      ))}
    </div>
  );
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const [displayContent, setDisplayContent] = useState(message.content);
  const pendingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (message.status !== "STREAMING") {
      setDisplayContent(message.content);
      return;
    }

    if (pendingRef.current) clearTimeout(pendingRef.current);
    pendingRef.current = setTimeout(() => setDisplayContent(message.content), DEBOUNCE_MS);
    return () => {
      if (pendingRef.current) clearTimeout(pendingRef.current);
    };
  }, [message.content, message.status]);

  const agentHue = useMemo(() => {
    const label = message.agent_running?.agent_name ?? message.role;
    return hashHue(label);
  }, [message.agent_running?.agent_name, message.role]);

  const copyText = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  if (isUser) {
    return (
      <div className="flex justify-end py-2">
        <div className="group max-w-[72%] rounded-[16px_16px_4px_16px] border border-[color:var(--accent)]/15 bg-[color:var(--accent-subtle)] px-4 py-3 text-sm leading-relaxed text-[color:var(--text-primary)] shadow-[var(--shadow-sm)]">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex gap-3 py-3">
      <AvatarMark />

      <div className="min-w-0 flex-1">
        {message.agent_running ? (
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-1)] px-2.5 py-1 text-xs text-[color:var(--text-secondary)] shadow-[var(--shadow-sm)]">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: `hsl(${agentHue} 85% 55%)` }}
            />
            {message.agent_running.agent_name}
          </div>
        ) : null}

        <div className={`relative rounded-3xl border border-transparent ${message.status === "STREAMING" ? "streaming-cursor" : ""}`}>
          {message.status === "PENDING" ? (
            <TypingDots />
          ) : (
            <div className="prose max-w-none text-sm prose-headings:tracking-tight prose-headings:text-[color:var(--text-primary)] prose-p:text-[color:var(--text-primary)] prose-strong:text-[color:var(--text-primary)] prose-a:text-[color:var(--accent)] prose-code:rounded prose-code:bg-[color:var(--surface-3)] prose-code:px-1 prose-code:py-0.5 prose-code:font-mono prose-code:text-[0.85em] prose-pre:rounded-2xl prose-pre:border prose-pre:border-[color:var(--border)] prose-pre:bg-[color:var(--surface-1)]">
              <ReactMarkdown
                components={{
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className ?? "");
                    const isBlock = !!match;
                    const text = String(children).replace(/\n$/, "");

                    if (isBlock) {
                      return (
                        <div className="my-3 overflow-hidden rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] shadow-[var(--shadow-sm)]">
                          <div className="flex items-center justify-between border-b border-[color:var(--border)] px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
                            <span>{match[1]}</span>
                            <button
                              onClick={() => navigator.clipboard.writeText(text)}
                              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] normal-case tracking-normal text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)]"
                            >
                              <Icon name="copy" className="h-3 w-3" />
                              Copy
                            </button>
                          </div>
                          <SyntaxHighlighter
                            language={match[1]}
                            style={oneDark}
                            customStyle={{
                              margin: 0,
                              padding: "1rem",
                              background: "transparent",
                              fontSize: "0.8125rem",
                              lineHeight: "1.6",
                            }}
                            showLineNumbers={text.split("\n").length > 6}
                          >
                            {text}
                          </SyntaxHighlighter>
                        </div>
                      );
                    }

                    return (
                      <code {...props} className="rounded bg-[color:var(--surface-3)] px-1.5 py-0.5 font-mono text-[0.84em] text-[color:var(--accent)]">
                        {children}
                      </code>
                    );
                  },
                  p({ children }) {
                    return <p className="mb-3 last:mb-0 leading-7">{children}</p>;
                  },
                  ul({ children }) {
                    return <ul className="mb-3 ml-5 list-disc space-y-1 last:mb-0">{children}</ul>;
                  },
                  ol({ children }) {
                    return <ol className="mb-3 ml-5 list-decimal space-y-1 last:mb-0">{children}</ol>;
                  },
                  li({ children }) {
                    return <li className="leading-7">{children}</li>;
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="my-3 border-l-2 border-[color:var(--accent-muted)] pl-4 italic text-[color:var(--text-secondary)]">
                        {children}
                      </blockquote>
                    );
                  },
                  h1({ children }) {
                    return <h1 className="mb-3 mt-4 text-xl font-semibold first:mt-0">{children}</h1>;
                  },
                  h2({ children }) {
                    return <h2 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h2>;
                  },
                  h3({ children }) {
                    return <h3 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h3>;
                  },
                  hr() {
                    return <hr className="my-4 border-[color:var(--border)]" />;
                  },
                  table({ children }) {
                    return (
                      <div className="my-3 overflow-x-auto rounded-2xl border border-[color:var(--border)]">
                        <table className="w-full text-sm">{children}</table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return <th className="border-b border-[color:var(--border)] bg-[color:var(--surface-2)] px-4 py-2.5 text-left text-xs font-semibold text-[color:var(--text-secondary)]">{children}</th>;
                  },
                  td({ children }) {
                    return <td className="border-b border-[color:var(--border)] px-4 py-2.5 text-sm text-[color:var(--text-primary)] last:border-0">{children}</td>;
                  },
                }}
              >
                {displayContent}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {message.status === "ERROR" && message.error ? (
          <div className="mt-3 flex items-start gap-2 rounded-2xl border border-[color:var(--danger)]/20 bg-[color:var(--danger)]/10 px-3 py-2 text-xs text-[color:var(--danger)]">
            <Icon name="alert-circle" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{message.error}</span>
          </div>
        ) : null}

        {message.citations.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {message.citations.map((citation, index) => (
              <CitationCard key={citation.citation_id} citation={citation} index={index} />
            ))}
          </div>
        ) : null}

        {message.artifacts.length > 0 ? (
          <div className="mt-3 space-y-2.5">
            {message.artifacts.map((artifact) => (
              <ArtifactRenderer key={artifact.artifact_id} artifact={artifact} />
            ))}
          </div>
        ) : null}

        <div className="mt-3 flex items-center justify-between opacity-0 transition-opacity group-hover:opacity-100">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={copyText}
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
            >
              <Icon name="copy" className="h-3.5 w-3.5" />
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("aura:regenerate", { detail: { messageId: message.message_id } }))}
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
            >
              <Icon name="refresh" className="h-3.5 w-3.5" />
              Regenerate
            </button>
          </div>

          <div className="flex items-center gap-1">
            <button type="button" className="rounded-full p-2 text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--success)]">
              <Icon name="check" className="h-3.5 w-3.5" />
            </button>
            <button type="button" className="rounded-full p-2 text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--danger)]">
              <Icon name="alert-circle" className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {message.status === "DONE" && message.trace_id ? (
          <p className="mt-2 text-[10px] text-[color:var(--text-tertiary)]">trace/{message.trace_id.slice(0, 8)}</p>
        ) : null}
      </div>
    </div>
  );
}

