import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "JuryAI — Hackathon Evaluator",
  description:
    "Upload and evaluate hackathon submissions (PDF/PPTX) with AI agents.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="app-header">
            <Link href="/" className="app-header__brand">
              <span className="app-header__brand-icon">J</span>
              JuryAI
            </Link>
            <nav className="app-header__nav">
              <Link href="/">Submit</Link>
              <Link href="/dashboard">Dashboard</Link>
            </nav>
            <div className="app-header__actions" />
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
