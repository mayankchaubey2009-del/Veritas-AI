import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VERITAS AI — Document Forensics & Contextual Intelligence Platform",
  description:
    "Enterprise AI-powered document forensics, visual anomaly inspection, contextual intelligence, and cross-document correlation platform.",
  icons: {
    icon: "/veritas-mark.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="veritas-grid-bg min-h-screen antialiased selection:bg-cyan-500/30 selection:text-cyan-200">
        {children}
      </body>
    </html>
  );
}
