"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { ChatArea } from "@/components/ChatArea";
import { useAuraStore } from "@/lib/store";
import { getMessages } from "@/lib/api";
import type { Message } from "@/lib/types";

function normalizeMessage(raw: Message): Message {
  return {
    ...raw,
    status: raw.status ?? "DONE",
    citations: raw.citations ?? [],
    artifacts: raw.artifacts ?? [],
  };
}

export default function ThreadPage() {
  const params = useParams();
  const threadId = params.threadId as string;

  const { threadMessages, setMessages, setActiveThread } = useAuraStore();

  useEffect(() => {
    setActiveThread(threadId);
  }, [threadId, setActiveThread]);

  // Load messages if not already in store
  useEffect(() => {
    if (threadMessages[threadId]) return;

    getMessages(threadId)
      .then(({ items }) => {
        setMessages(threadId, items.map(normalizeMessage));
      })
      .catch(() => {
        // If endpoint not available, set empty so we don't retry on every render
        setMessages(threadId, []);
      });
  }, [threadId, threadMessages, setMessages]);

  return (
    <div className="h-full">
      <ChatArea threadId={threadId} />
    </div>
  );
}
