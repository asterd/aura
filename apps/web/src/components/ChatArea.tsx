"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuraStore } from "@/lib/store";
import { MessageBubble } from "./MessageBubble";
import { Composer } from "./Composer";
import { OnboardingBanner } from "./OnboardingBanner";
import { CreateSpaceModal } from "./CreateSpaceModal";
import type { Space } from "@/lib/types";
import { Avatar, Badge, Button, Card, Input } from "./ui";
import { Icon } from "./icons";

interface Props {
  threadId: string | null;
}

const STARTER_PROMPTS = [
  {
    label: "Summarize a document",
    icon: "📄",
    prompt: "Can you summarize the key points of a document I'll share?",
    description: "Extract the main arguments and actionable takeaways.",
  },
  {
    label: "Draft an email",
    icon: "✉️",
    prompt: "Help me write a professional email to a client about a project update.",
    description: "Keep the tone concise and stakeholder-ready.",
  },
  {
    label: "Explain a concept",
    icon: "💡",
    prompt: "Explain a complex concept in simple terms.",
    description: "Give me a clear, structured explanation.",
  },
  {
    label: "Analyze data",
    icon: "📊",
    prompt: "Help me analyze and interpret some data patterns.",
    description: "Highlight trends, outliers and next steps.",
  },
] as const;

function PromptCard({
  label,
  icon,
  description,
  prompt,
}: (typeof STARTER_PROMPTS)[number]) {
  return (
    <button
      onClick={() => window.dispatchEvent(new CustomEvent("aura:starter-prompt", { detail: { prompt } }))}
      className="group rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] p-4 text-left transition-all duration-150 hover:-translate-y-0.5 hover:border-[color:var(--accent)]/30 hover:bg-[color:var(--surface-hover)]"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl brand-gradient text-lg shadow-[var(--shadow-sm)]">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[color:var(--text-primary)]">{label}</p>
          <p className="mt-1 text-xs text-[color:var(--text-secondary)]">{description}</p>
        </div>
      </div>
    </button>
  );
}

function ThreadHeader({
  title,
  onTitleChange,
  spaces,
  onRemoveSpace,
}: {
  title: string;
  onTitleChange: (value: string) => void;
  spaces: Space[];
  onRemoveSpace: (spaceId: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(title);

  useEffect(() => setValue(title), [title]);

  return (
    <div className="mb-4 rounded-3xl border border-[color:var(--border)] bg-[color:var(--surface-1)]/80 p-4 shadow-[var(--shadow-sm)] backdrop-blur-xl">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 flex-1">
          {editing ? (
            <Input
              value={value}
              autoFocus
              onChange={(event) => setValue(event.target.value)}
              onBlur={() => {
                onTitleChange(value.trim() || "Untitled conversation");
                setEditing(false);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onTitleChange(value.trim() || "Untitled conversation");
                  setEditing(false);
                }
                if (event.key === "Escape") {
                  setValue(title);
                  setEditing(false);
                }
              }}
              className="text-lg font-semibold"
            />
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-left text-lg font-semibold tracking-tight text-[color:var(--text-primary)]"
            >
              {title}
            </button>
          )}
          <p className="mt-1 text-sm text-[color:var(--text-secondary)]">Chat in the context of projects, spaces and agents.</p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm">
            <Icon name="sliders" className="h-4 w-4" />
            <span className="hidden sm:inline">Options</span>
          </Button>
          <Button variant="ghost" size="sm">
            <Icon name="more" className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {spaces.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {spaces.map((space) => (
            <Badge key={space.id} tone="accent" className="gap-1 pr-1.5">
              <span>#{space.name}</span>
              <button
                type="button"
                onClick={() => onRemoveSpace(space.id)}
                className="ml-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] hover:bg-[color:var(--surface-hover)]"
              >
                ×
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ChatArea({ threadId }: Props) {
  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const { threadMessages, isStreaming, threads, availableSpaces, activeSpaceIds, setActiveSpaceIds, upsertThread } = useAuraStore();
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [title, setTitle] = useState("New chat");

  const messages = threadId ? (threadMessages[threadId] ?? []) : [];
  const currentThread = threadId ? threads.find((thread) => thread.id === threadId) : null;
  const activeSpaceList = threadId
    ? availableSpaces.filter((space) => (activeSpaceIds[threadId] ?? []).includes(space.id))
    : availableSpaces.slice(0, 1);

  useEffect(() => {
    setTitle(currentThread?.title ?? (threadId ? "Untitled conversation" : "Start a conversation"));
  }, [currentThread?.title, threadId]);

  useEffect(() => {
    if (!threadId || !currentThread) return;
    upsertThread({ ...currentThread, title });
  }, [currentThread, threadId, title, upsertThread]);

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages.length, isStreaming]);

  const lastMessage = messages[messages.length - 1];
  useEffect(() => {
    if (lastMessage?.status === "STREAMING") scrollToBottom();
  }, [lastMessage?.content, lastMessage?.status]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setShowScrollButton(distFromBottom > 200);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const handleNewThread = (id: string) => {
    router.push(`/chat/${id}`);
  };

  const handleRemoveSpace = (spaceId: string) => {
    if (!threadId) return;
    const current = activeSpaceIds[threadId] ?? [];
    setActiveSpaceIds(threadId, current.filter((id) => id !== spaceId));
  };

  return (
    <div className="relative flex h-full min-h-screen flex-col bg-[color:var(--bg-base)]">
      <CreateSpaceModal
        open={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={() => setCreateSpaceOpen(false)}
      />

      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-chat flex-col px-4 py-5 md:px-6 md:py-6">
          <OnboardingBanner onCreateSpace={() => setCreateSpaceOpen(true)} />

          {threadId ? (
            <ThreadHeader
              title={title}
              onTitleChange={setTitle}
              spaces={activeSpaceList}
              onRemoveSpace={handleRemoveSpace}
            />
          ) : (
            <div className="mb-5 flex items-center justify-between rounded-3xl border border-[color:var(--border)] bg-[color:var(--surface-1)]/80 px-4 py-3 shadow-[var(--shadow-sm)] backdrop-blur-xl">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">Chat</p>
                <h1 className="mt-1 text-lg font-semibold tracking-tight text-[color:var(--text-primary)]">Ask AURA</h1>
              </div>
              <Button variant="secondary" size="sm" onClick={() => setCreateSpaceOpen(true)}>
                New Space
              </Button>
            </div>
          )}

          {messages.length === 0 ? (
            <div className="flex flex-col gap-8 py-8 md:py-12">
              <div className="flex flex-col items-center gap-4 text-center">
                <Avatar label="AURA" size={56} />
                <div className="max-w-2xl">
                  <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
                    Ciao, {threadId ? "come possiamo continuare?" : "come posso aiutarti oggi?"}
                  </h2>
                  <p className="mt-2 text-sm text-[color:var(--text-secondary)]">
                    Scrivi una richiesta, aggiungi uno space con <span className="font-mono">#</span> o coinvolgi un agente con <span className="font-mono">@</span>.
                  </p>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <PromptCard key={prompt.label} {...prompt} />
                ))}
              </div>

              <div className="mx-auto grid max-w-2xl gap-3 sm:grid-cols-2">
                <Card className="p-4">
                  <p className="text-sm font-semibold text-[color:var(--text-primary)]">Projects</p>
                  <p className="mt-1 text-sm text-[color:var(--text-secondary)]">Navigate workspaces from the left rail and context panel.</p>
                </Card>
                <Card className="p-4">
                  <p className="text-sm font-semibold text-[color:var(--text-primary)]">Spaces</p>
                  <p className="mt-1 text-sm text-[color:var(--text-secondary)]">Ground responses on documents, web pages and APIs.</p>
                </Card>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {messages.map((msg) => (
                <MessageBubble key={msg.message_id} message={msg} />
              ))}
              <div ref={messagesEndRef} className="h-8" />
            </div>
          )}
        </div>
      </div>

      {showScrollButton ? (
        <button
          onClick={() => scrollToBottom()}
          className="fixed bottom-28 right-4 z-20 flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-1)] px-4 py-2 text-xs text-[color:var(--text-secondary)] shadow-[var(--shadow-md)] backdrop-blur-xl transition-all hover:bg-[color:var(--surface-hover)] md:right-6"
        >
          <Icon name="arrow-down" className="h-3.5 w-3.5" />
          Scroll to bottom
        </button>
      ) : null}

      <div className="sticky bottom-0 shrink-0 border-t border-[color:var(--border)] bg-[color:var(--surface-1)]/80 px-4 py-3 backdrop-blur-xl md:px-6 md:py-4">
        <div className="mx-auto max-w-chat">
          <Composer threadId={threadId} onNewThread={handleNewThread} />
        </div>
      </div>
    </div>
  );
}
