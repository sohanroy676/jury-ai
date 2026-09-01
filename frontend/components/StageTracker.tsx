"use client";

export interface StageState {
  parsed: boolean;
  scored: boolean;
  verdict: "shortlist" | "reject" | null;
}

const PIPELINE_STEPS = [
  { key: "submitted", label: "Submitted" },
  { key: "parsed", label: "Parsed" },
  { key: "scored", label: "Scored" },
] as const;

export default function StageTracker({ state }: { state: StageState }) {
  const reached = { submitted: true, ...state };
  const doneCount = PIPELINE_STEPS.filter(
    (step) => reached[step.key as keyof typeof reached]
  ).length;

  return (
    <ol className="stage-tracker" aria-label="Submission progress">
      {PIPELINE_STEPS.map((step, index) => {
        const isDone = index < doneCount;
        return (
          <li
            key={step.key}
            className={isDone ? "stage-done" : "stage-todo"}
          >
            <span>{isDone ? "✓" : index + 1}</span> {step.label}
          </li>
        );
      })}
      <li className={state.verdict ? "stage-done stage-verdict" : "stage-todo"}>
        <span>{state.verdict ? "★" : "4"}</span>
        {state.verdict === "shortlist"
          ? "Shortlisted"
          : state.verdict === "reject"
            ? "Rejected"
            : "Awaiting result"}
      </li>
    </ol>
  );
}
