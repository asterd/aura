"use client";

import { useEffect } from "react";
import { Button, Card } from "@/components/ui";
import { Icon } from "@/components/icons";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="it">
      <body className="min-h-screen bg-[color:var(--bg-base)] p-6 text-[color:var(--text-primary)]">
        <div className="mx-auto flex min-h-screen max-w-2xl items-center">
          <Card className="w-full p-6">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl brand-gradient text-white">
                <Icon name="alert-circle" className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <h1 className="text-2xl font-semibold tracking-tight">Qualcosa è andato storto</h1>
                <p className="mt-2 text-sm text-[color:var(--text-secondary)]">
                  Riprova a caricare la pagina o torna alla chat.
                </p>
                {process.env.NODE_ENV !== "production" ? (
                  <details className="mt-4 rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-2)] p-4 text-xs text-[color:var(--text-secondary)]">
                    <summary className="cursor-pointer font-medium text-[color:var(--text-primary)]">Stack trace</summary>
                    <pre className="mt-3 whitespace-pre-wrap break-words font-mono">{error.message}</pre>
                  </details>
                ) : null}
                <div className="mt-5 flex flex-wrap gap-3">
                  <Button onClick={reset}>
                    <Icon name="refresh" className="h-4 w-4" />
                    Ricarica
                  </Button>
                  <Button variant="secondary" onClick={() => window.location.assign("/chat")}>
                    Torna alla chat
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </body>
    </html>
  );
}

