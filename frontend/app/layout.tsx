import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "JuryAI — Hackathon AI Jury System",
  description:
    "Automated, multi-agent AI scoring, ranking, explainability, and appeals for hackathon submissions.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="app-shell">
          <header className="app-header">
            <Link href="/" className="app-header__brand">
              <span className="app-header__brand-icon">J</span>
              JuryAI
            </Link>
            <nav className="app-header__nav">
              <Link href="/">Submit Proposal</Link>
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/dashboard/appeals">Appeals</Link>
              <Link href="/dashboard/analytics">Analytics</Link>
              <Link href="/dashboard/tracks">Tracks</Link>
            </nav>
            <div className="app-header__actions">
              <span className="badge badge--ai">
                ⚡ 4 AI Scoring Agents Active
              </span>
            </div>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
