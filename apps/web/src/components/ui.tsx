"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "./icons";

const baseButton =
  "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}) {
  const sizes = {
    sm: "px-3 py-1.5 text-xs rounded-lg",
    md: "px-4 py-2 text-sm",
    lg: "px-5 py-2.5 text-base rounded-2xl",
  }[size];
  const variants = {
    primary: "brand-gradient text-white shadow-[var(--shadow-accent)] hover:opacity-95",
    secondary: "border border-[color:var(--border)] bg-[color:var(--surface-1)] text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]",
    ghost: "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
    danger: "bg-[color:var(--danger)] text-white hover:opacity-95",
  }[variant];

  return (
    <button {...props} className={`${baseButton} ${sizes} ${variants} ${className}`}>
      {children}
    </button>
  );
}

export function LinkButton({
  children,
  variant = "secondary",
  className = "",
  ...props
}: React.ComponentProps<typeof Link> & {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
}) {
  const variants = {
    primary: "brand-gradient text-white shadow-[var(--shadow-accent)]",
    secondary: "border border-[color:var(--border)] bg-[color:var(--surface-1)] text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]",
    ghost: "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
  }[variant];

  return (
    <Link
      {...props}
      className={`${baseButton} ${variants} ${className}`}
    >
      {children}
    </Link>
  );
}

export function Input({
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder:text-[color:var(--text-tertiary)] outline-none transition-all focus:border-[color:var(--accent)] ${className}`}
    />
  );
}

export function Textarea({
  className = "",
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full rounded-xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder:text-[color:var(--text-tertiary)] outline-none transition-all focus:border-[color:var(--accent)] ${className}`}
    />
  );
}

export function Select({
  className = "",
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full rounded-xl border border-[color:var(--border)] bg-[color:var(--surface-1)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none transition-all focus:border-[color:var(--accent)] ${className}`}
    />
  );
}

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "accent";
  className?: string;
}) {
  const styles = {
    neutral: "bg-[color:var(--surface-2)] text-[color:var(--text-secondary)]",
    success: "bg-[color:var(--success)]/10 text-[color:var(--success)]",
    warning: "bg-[color:var(--warning)]/12 text-[color:var(--warning)]",
    danger: "bg-[color:var(--danger)]/10 text-[color:var(--danger)]",
    accent: "bg-[color:var(--accent-subtle)] text-[color:var(--accent)]",
  }[tone];

  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${styles} ${className}`}>{children}</span>;
}

export function Avatar({
  label,
  src,
  size = 40,
}: {
  label: string;
  src?: string | null;
  size?: number;
}) {
  const initials = label
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div
      className="flex shrink-0 items-center justify-center overflow-hidden rounded-full text-xs font-semibold text-white"
      style={{
        width: size,
        height: size,
        background: "var(--gradient-brand)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {src ? (
        // Tenant branding may point to arbitrary image URLs.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={label} className="h-full w-full object-cover" />
      ) : (
        initials || <Icon name="user" className="h-4 w-4" />
      )}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-[color:var(--border)] bg-[color:var(--surface-1)] shadow-[var(--shadow-sm)] ${className}`}>
      {children}
    </div>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`p-5 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-[color:var(--text-primary)]">{title}</h2>
          {description ? <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">{description}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </Card>
  );
}

export function PageHeader({
  title,
  description,
  action,
  breadcrumb,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  breadcrumb?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="space-y-2">
        {breadcrumb}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">{title}</h1>
          {description ? <p className="mt-1 max-w-2xl text-sm text-[color:var(--text-secondary)]">{description}</p> : null}
        </div>
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center justify-center gap-4 px-6 py-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl brand-gradient text-white">
        <Icon name="logo" className="h-5 w-5" />
      </div>
      <div>
        <h3 className="text-base font-semibold">{title}</h3>
        {description ? <p className="mt-1 text-sm text-[color:var(--text-secondary)]">{description}</p> : null}
      </div>
      {action}
    </Card>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-xl bg-[linear-gradient(90deg,rgba(148,163,184,0.08),rgba(148,163,184,0.18),rgba(148,163,184,0.08))] bg-[length:200%_100%] ${className}`}
      style={{ animation: "shimmer 1.4s linear infinite" }}
    />
  );
}

export function StatCard({
  label,
  value,
  sublabel,
  icon,
}: {
  label: string;
  value: string;
  sublabel?: string;
  icon?: ReactNode;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-[color:var(--text-tertiary)]">{label}</p>
          <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
          {sublabel ? <p className="mt-1 text-xs text-[color:var(--text-secondary)]">{sublabel}</p> : null}
        </div>
        {icon ? <div className="rounded-xl bg-[color:var(--accent-subtle)] p-2 text-[color:var(--accent)]">{icon}</div> : null}
      </div>
    </Card>
  );
}
