import Link from "next/link";

/** Shared navigation between the upload portal and the evaluator dashboard. */
export default function NavLinks() {
  return (
    <nav className="nav-links" aria-label="Main navigation">
      <Link href="/">Upload portal</Link>
      {" · "}
      <Link href="/dashboard">Evaluator dashboard</Link>
      {" · "}
      <Link href="/dashboard/appeals">Appeals</Link>
    </nav>
  );
}
