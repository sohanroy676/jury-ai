import Link from "next/link";

/** Shared navigation bar between the upload portal and evaluator dashboard surfaces. */
export default function NavLinks() {
  return (
    <nav className="nav-links" aria-label="Main navigation">
      <Link href="/">Upload portal</Link>
      <span style={{ opacity: 0.3 }}>·</span>
      <Link href="/dashboard">Evaluator dashboard</Link>
      <span style={{ opacity: 0.3 }}>·</span>
      <Link href="/dashboard/appeals">Appeals</Link>
      <span style={{ opacity: 0.3 }}>·</span>
      <Link href="/dashboard/analytics">Analytics</Link>
      <span style={{ opacity: 0.3 }}>·</span>
      <Link href="/dashboard/tracks">Tracks</Link>
    </nav>
  );
}
