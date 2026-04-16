"use client";

import { type ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/icons";

type Theme = "dark" | "light" | "system";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: "dark" | "light";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "system",
  resolvedTheme: "light",
  setTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

type ToastType = "success" | "error" | "warning" | "info";

type ToastEntry = {
  id: string;
  title?: string;
  message: string;
  type: ToastType;
};

type ToastContextValue = {
  pushToast: (toast: Omit<ToastEntry, "id">) => void;
};

const ToastContext = createContext<ToastContextValue>({
  pushToast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

type BrandingState = {
  brandName: string;
  brandPrimary: string;
  brandSecondary: string;
  brandLogoUrl?: string | null;
};

const DEFAULT_BRANDING: BrandingState = {
  brandName: "AURA",
  brandPrimary: "#6366f1",
  brandSecondary: "#06b6d4",
  brandLogoUrl: null,
};

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = theme === "dark" || (theme === "system" && prefersDark);
  root.classList.toggle("dark", isDark);
  root.style.colorScheme = isDark ? "dark" : "light";
  return isDark ? "dark" : "light";
}

function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">("light");

  useEffect(() => {
    const stored = window.localStorage.getItem("aura-theme") as Theme | null;
    const initial = stored ?? "system";
    setThemeState(initial);
    setResolvedTheme(applyTheme(initial));

    const root = document.documentElement;
    root.style.setProperty("--brand-primary", DEFAULT_BRANDING.brandPrimary);
    root.style.setProperty("--brand-secondary", DEFAULT_BRANDING.brandSecondary);
    root.style.setProperty("--brand-name", DEFAULT_BRANDING.brandName);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadBranding() {
      try {
        const response = await fetch("/api/v1/tenant/branding", { credentials: "include" });
        if (!response.ok) return;
        const branding = (await response.json()) as Partial<BrandingState>;
        if (cancelled) return;

        const root = document.documentElement;
        const brandName = branding.brandName ?? DEFAULT_BRANDING.brandName;
        const brandPrimary = branding.brandPrimary ?? DEFAULT_BRANDING.brandPrimary;
        const brandSecondary = branding.brandSecondary ?? DEFAULT_BRANDING.brandSecondary;

        root.style.setProperty("--brand-primary", brandPrimary);
        root.style.setProperty("--brand-secondary", brandSecondary);
        root.style.setProperty("--brand-name", brandName);
        if (branding.brandLogoUrl) {
          root.style.setProperty("--brand-logo-url", `url(${branding.brandLogoUrl})`);
        }
      } catch {
        // Optional tenant branding.
      }
    }

    void loadBranding();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const next = applyTheme(theme);
    setResolvedTheme(next);
    window.localStorage.setItem("aura-theme", theme);

    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => setResolvedTheme(applyTheme("system"));
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme: setThemeState }}>
      {children}
    </ThemeContext.Provider>
  );
}

function ToastStack() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);

  useEffect(() => {
    const handleToast = (event: Event) => {
      const detail = (event as CustomEvent<Partial<ToastEntry>>).detail;
      if (!detail?.message) return;

      const entry: ToastEntry = {
        id: crypto.randomUUID(),
        message: detail.message,
        title: detail.title,
        type: detail.type ?? "info",
      };

      setToasts((current) => [entry, ...current].slice(0, 3));

      const timeout = entry.type === "error" ? 6000 : entry.type === "warning" ? 5000 : 4000;
      window.setTimeout(() => {
        setToasts((current) => current.filter((toast) => toast.id !== entry.id));
      }, timeout);
    };

    window.addEventListener("aura:toast", handleToast as EventListener);
    return () => window.removeEventListener("aura:toast", handleToast as EventListener);
  }, []);

  const tones = useMemo(
    () => ({
      success: "border-[color:var(--success)]/30 bg-[color:var(--success)]/10",
      error: "border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10",
      warning: "border-[color:var(--warning)]/30 bg-[color:var(--warning)]/12",
      info: "border-[color:var(--info)]/30 bg-[color:var(--info)]/10",
    }),
    []
  );

  return (
    <div className="fixed bottom-4 right-4 z-[80] flex w-[min(100vw-2rem,22rem)] flex-col gap-2 md:bottom-6 md:right-6">
      {toasts.map((toast) => (
        <div key={toast.id} className={`rounded-2xl border px-4 py-3 shadow-[var(--shadow-lg)] backdrop-blur-xl ${tones[toast.type]}`}>
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-[color:var(--surface-1)] p-1 text-[color:var(--accent)]">
              <Icon
                name={toast.type === "error" ? "alert-circle" : toast.type === "success" ? "check" : toast.type === "warning" ? "alert-circle" : "info"}
                className="h-3.5 w-3.5"
              />
            </div>
            <div className="min-w-0 flex-1">
              {toast.title ? <p className="text-sm font-semibold text-[color:var(--text-primary)]">{toast.title}</p> : null}
              <p className="text-sm text-[color:var(--text-secondary)]">{toast.message}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ToastProvider({ children }: { children: ReactNode }) {
  const pushToast = (toast: Omit<ToastEntry, "id">) => {
    window.dispatchEvent(new CustomEvent("aura:toast", { detail: toast }));
  };

  return (
    <ToastContext.Provider value={{ pushToast }}>
      {children}
      <ToastStack />
    </ToastContext.Provider>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <ToastProvider>{children}</ToastProvider>
    </ThemeProvider>
  );
}

