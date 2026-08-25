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
      <body>{children}</body>
    </html>
  );
}
