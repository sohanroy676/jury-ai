"use client";

// v1.1.0 status tracker: renders the submission pipeline as a stepper.
// Stages are DERIVED upstream (parsed row present, complete score set,
// feedback verdict) rather than stored, matching the project's
// compute-on-the-fly convention.
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
      {PIPELINE_STEPS.map((step, index) => (
        <li
          key={step.key}
          className={index < doneCount ? "stage-done" : "stage-todo"}
        >
          {step.label}
        </li>
      ))}
      <li className={state.verdict ? "stage-done stage-verdict" : "stage-todo"}>
        {state.verdict === "shortlist"
          ? "Shortlisted"
          : state.verdict === "reject"
            ? "Rejected"
            : "Awaiting result"}
      </li>
    </ol>
  );
}
