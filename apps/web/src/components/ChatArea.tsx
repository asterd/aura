"use client";

import { useEffect, useRef, useState } from "react";
import { useAuraStore } from "@/lib/store";
import { MessageBubble } from "./MessageBubble";
import { Composer } from "./Composer";
import { OnboardingBanner } from "./OnboardingBanner";
import { CreateSpaceModal } from "./CreateSpaceModal";
import { useRouter } from "next/navigation";

interface Props {
  threadId: string | null;
}

export function ChatArea({ threadId }: Props) {
  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { threadMessages, isStreaming } = useAuraStore();
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);

  const messages = threadId ? (threadMessages[threadId] ?? []) : [];

  // Auto-scroll to bottom when new messages arrive or streaming
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isStreaming]);

  // Also scroll during streaming (content grows)
  const lastMessage = messages[messages.length - 1];
  useEffect(() => {
    if (lastMessage?.status === "STREAMING") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [lastMessage?.content, lastMessage?.status]);

  const handleNewThread = (id: string) => {
    router.push(`/chat/${id}`);
  };

  return (
    <div className="flex flex-col h-full">
      <CreateSpaceModal
        open={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={() => {
          // Space added to store by CreateSpaceModal — banner will auto-hide
        }}
      />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto py-4 space-y-1">
        <OnboardingBanner onCreateSpace={() => setCreateSpaceOpen(true)} />
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4 py-20">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold"
              style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            >
              A
            </div>
            <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
              How can I help you today?
            </h2>
            <p className="text-sm text-center max-w-sm" style={{ color: "var(--muted-foreground)" }}>
              Ask questions, search your knowledge spaces, or run agents with @mention.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.message_id} message={msg} />
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Composer */}
      <div
        className="flex-shrink-0 p-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Composer threadId={threadId} onNewThread={handleNewThread} />
      </div>
    </div>
  );
}
