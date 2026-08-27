import AppealsQueueView from "../../components/AppealsQueueView";

// Thin server wrapper (mirrors app/submissions/[id]/page.tsx): all logic
// lives in the client component so Vitest exercises props directly.
export default function AppealsPage() {
  return <AppealsQueueView />;
}
