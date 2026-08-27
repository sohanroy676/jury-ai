"use client";

import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "./ErrorBanner";
import NavLinks from "./NavLinks";
import {
  ApiError,
  Appeal,
  AppealDecision,
  AppealStatus,
  fetchAppeals,
  resolveAppeal,
} from "../lib/api";

export default function AppealsQueueView() {
  const [appeals, setAppeals] = useState<Appeal[] | null>(null);
  const [filter, setFilter] = useState<AppealStatus>("open");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-appeal resolve form state.
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [evaluator, setEvaluator] = useState("");

  const load = useCallback(async (status: AppealStatus) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAppeals(status);
      setAppeals(data.appeals);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Unexpected error loading the appeals queue."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filter);
  }, [load, filter]);

  async function handleResolve(
    appealId: string,
    decision: AppealDecision,
    note: string
  ) {
    if (!evaluator.trim()) {
      setError("Enter your evaluator name before resolving an appeal.");
      return;
    }
    setResolvingId(appealId);
    setError(null);
    try {
      await resolveAppeal(appealId, {
        decision,
        decisionNote: note,
        evaluator: evaluator.trim(),
      });
      await load(filter);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Unexpected error resolving the appeal."
      );
    } finally {
      setResolvingId(null);
    }
  }

  return (
    <main>
      <NavLinks />
      <h1>Appeals queue</h1>
      <p className="hint">
        Human-evaluator queue. Each appeal carries the original AI scoring and
        feedback so the decision is made in full context.
      </p>

      <div className="inline-controls">
        <label htmlFor="appeal-filter">Show</label>
        <select
          id="appeal-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value as AppealStatus)}
        >
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>

      <div className="inline-controls">
        <label htmlFor="evaluator-name">Evaluator name</label>
        <input
          id="evaluator-name"
          type="text"
          value={evaluator}
          onChange={(e) => setEvaluator(e.target.value)}
          placeholder="your name (logged on decisions)"
        />
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {loading ? (
        <p className="hint">Loading appeals…</p>
      ) : appeals && appeals.length === 0 ? (
        <p className="hint">
          {filter === "open"
            ? "No open appeals. Publish results to open the appeal window."
            : "No resolved appeals yet."}
        </p>
      ) : (
        <ul className="appeal-list">
          {(appeals ?? []).map((appeal) => (
            <AppealCard
              key={appeal.id}
              appeal={appeal}
              resolving={resolvingId === appeal.id}
              onResolve={(decision, note) =>
                void handleResolve(appeal.id, decision, note)
              }
            />
          ))}
        </ul>
      )}
    </main>
  );
}

function AppealCard({
  appeal,
  resolving,
  onResolve,
}: {
  appeal: Appeal;
  resolving: boolean;
  onResolve: (decision: AppealDecision, note: string) => void;
}) {
  const [note, setNote] = useState("");
  const ctx = appeal.context;
  const badge =
    appeal.status === "open"
      ? "badge badge-tie"
      : appeal.decision === "upheld"
        ? "badge badge-shortlist"
        : "badge badge-reject";

  return (
    <li className="card appeal-card">
      <p>
        <span className={badge}>
          {appeal.status}
          {appeal.decision ? ` · ${appeal.decision}` : ""}
        </span>
        <span className="meta">
          {" "}
          {ctx?.team_name ?? appeal.submission_id} · filed {appeal.created_at}
        </span>
      </p>
      <p>
        <b>Reason:</b> {appeal.reason}
      </p>

      {ctx && <AppealContextView ctx={ctx} />}

      {appeal.status === "open" ? (
        <div className="inline-controls">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="decision note (optional)"
          />
          <button
            type="button"
            disabled={resolving}
            onClick={() => onResolve("upheld", note.trim())}
          >
            {resolving ? "Resolving…" : "Upheld"}
          </button>
          <button
            type="button"
            disabled={resolving}
            onClick={() => onResolve("dismissed", note.trim())}
          >
            {resolving ? "Resolving…" : "Dismissed"}
          </button>
        </div>
      ) : (
        appeal.decision_note && (
          <p className="hint">Evaluator note: {appeal.decision_note}</p>
        )
      )}
    </li>
  );
}

function AppealContextView({ ctx }: { ctx: NonNullable<Appeal["context"]> }) {
  return (
    <div className="appeal-context">
      <p className="hint">
        Original result: composite{" "}
        {ctx.composite_score != null ? ctx.composite_score.toFixed(2) : "—"} ·
        rank {ctx.rank ?? "—"}
        {ctx.shortlisted != null
          ? ctx.shortlisted
            ? " · shortlisted"
            : " · not shortlisted"
          : ""}
      </p>
      <h4>Criterion scores</h4>
      {ctx.scores.length > 0 ? (
        <table className="scores">
          <thead>
            <tr>
              <th>Criterion</th>
              <th>Score</th>
              <th>Justification</th>
            </tr>
          </thead>
          <tbody>
            {ctx.scores.map((s) => (
              <tr key={s.criterion}>
                <td>{s.criterion.replace(/_/g, " ")}</td>
                <td>{s.score}</td>
                <td>{s.justification}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="hint">No scores attached.</p>
      )}
      {ctx.feedback ? (
        <div className="feedback-card">
          <p>
            <b>Verdict:</b> {ctx.feedback.verdict}
          </p>
          <h4>Strengths</h4>
          <ul>
            {ctx.feedback.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
          <h4>Weaknesses</h4>
          <ul>
            {ctx.feedback.weaknesses.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
          <h4>Suggested next step</h4>
          <p>{ctx.feedback.suggestion}</p>
        </div>
      ) : (
        <p className="hint">No feedback attached.</p>
      )}
    </div>
  );
}

