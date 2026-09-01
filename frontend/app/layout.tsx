import type { Metadata } from "next";
import { Inter, Outfit, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

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
    <html
      lang="en"
      className={`${inter.variable} ${outfit.variable} ${jetbrainsMono.variable}`}
    >
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
