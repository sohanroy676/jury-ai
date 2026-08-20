import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JuryAI — Hackathon Submission Portal",
  description: "Upload your hackathon submission (PDF or PPTX).",
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
