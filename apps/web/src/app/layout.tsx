import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { AppShell } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: {
    template: "%s — AURA",
    default: "AURA",
  },
  description: "Modern AI workspace for chat, projects, spaces and administration.",
  applicationName: "AURA",
  authors: [{ name: "AURA" }],
  keywords: ["AI", "RAG", "agents", "knowledge", "enterprise"],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafbff" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0f1a" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="it" suppressHydrationWarning>
      <body className="font-sans">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
