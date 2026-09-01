import type { Metadata } from "next";
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
            <a href="/" className="app-header__brand">
              <span className="app-header__brand-icon">J</span>
              JuryAI
            </a>
            <nav className="app-header__nav">
              <a href="/">Submit</a>
              <a href="/dashboard">Dashboard</a>
            </nav>
            <div className="app-header__actions" />
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
