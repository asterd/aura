"use client";

import { useState } from "react";
import { useAuraStore } from "@/lib/store";

interface Props {
  onCreateSpace: () => void;
}

export function OnboardingBanner({ onCreateSpace }: Props) {
  const { availableSpaces } = useAuraStore();
  const [dismissed, setDismissed] = useState(false);

  // Show only when: no spaces available AND not dismissed
  if (availableSpaces.length > 0 || dismissed) return null;

  return (
    <div
      className="mx-4 mt-4 rounded-2xl p-5"
      style={{
        backgroundColor: "rgba(99,102,241,0.08)",
        border: "1px solid rgba(99,102,241,0.2)",
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
              Welcome to AURA
            </h3>
            <p className="text-xs mt-1" style={{ color: "var(--muted-foreground)" }}>
              You can chat freely with the AI, or create a Knowledge Space to chat with your company
              documents.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={onCreateSpace}
              className="px-3 py-1.5 rounded-lg text-xs font-medium"
              style={{
                backgroundColor: "var(--accent)",
                color: "var(--accent-foreground)",
              }}
            >
              Create Knowledge Space
            </button>
            <button
              onClick={() => setDismissed(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium"
              style={{
                backgroundColor: "var(--surface-raised)",
                color: "var(--muted-foreground)",
                border: "1px solid var(--border)",
              }}
            >
              Start chatting freely
            </button>
          </div>

          <div className="grid grid-cols-3 gap-3 mt-2">
            {[
              { step: "1", text: "Create a Space", icon: "🗂️" },
              { step: "2", text: "Upload documents", icon: "📄" },
              { step: "3", text: "Chat with your data", icon: "💬" },
            ].map(({ step, text, icon }) => (
              <div
                key={step}
                className="flex flex-col items-center gap-1 p-2 rounded-xl text-center"
                style={{ backgroundColor: "var(--surface-raised)" }}
              >
                <span className="text-lg">{icon}</span>
                <span className="text-xs font-medium" style={{ color: "var(--foreground)" }}>
                  {step}. {text}
                </span>
              </div>
            ))}
          </div>
        </div>

        <button
          onClick={() => setDismissed(true)}
          className="flex-shrink-0 opacity-50 hover:opacity-100"
          style={{ color: "var(--muted-foreground)" }}
          aria-label="Dismiss"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
