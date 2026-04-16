"use client";

import { useEffect, useState } from "react";
import { useAuraStore } from "@/lib/store";
import { Button, Card } from "./ui";
import { Icon } from "./icons";

interface Props {
  onCreateSpace: () => void;
}

const STORAGE_KEY = "aura-onboarding-dismissed";

export function OnboardingBanner({ onCreateSpace }: Props) {
  const { availableSpaces } = useAuraStore();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    setDismissed(window.localStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  if (availableSpaces.length > 0 || dismissed) return null;

  const dismiss = () => {
    window.localStorage.setItem(STORAGE_KEY, "true");
    setDismissed(true);
  };

  return (
    <Card className="relative mb-5 overflow-hidden border-[color:var(--accent)]/15 bg-[linear-gradient(135deg,rgba(99,102,241,0.09),rgba(6,182,212,0.04))]">
      <div className="flex flex-col gap-5 p-5 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl brand-gradient text-white shadow-[var(--shadow-accent)]">
            <Icon name="logo" className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[color:var(--text-primary)]">Onboarding</p>
            <p className="mt-1 max-w-2xl text-sm text-[color:var(--text-secondary)]">
              Create a Knowledge Space, upload documents and start grounded conversations.
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              {[
                ["1", "Create a Space"],
                ["2", "Upload docs"],
                ["3", "Chat with data"],
              ].map(([step, label]) => (
                <div key={step} className="rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">Step {step}</p>
                  <p className="mt-1 text-sm font-medium text-[color:var(--text-primary)]">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <Button onClick={onCreateSpace}>
            <Icon name="plus" className="h-4 w-4" />
            Create Knowledge Space
          </Button>
          <Button variant="secondary" onClick={dismiss}>
            Start chatting freely
          </Button>
        </div>
      </div>
      <button
        onClick={dismiss}
        className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-[color:var(--text-tertiary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
        aria-label="Dismiss onboarding"
      >
        <Icon name="chevron-left" className="h-4 w-4 rotate-180" />
      </button>
    </Card>
  );
}
