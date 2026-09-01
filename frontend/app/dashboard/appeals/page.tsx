"use client";

import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import NavLinks from "@/components/NavLinks";
import {
  ApiError,
  AppealQueueItem,
  AppealStatus,
  fetchAppeals,
  resolveAppeal,
} from "@/lib/api";

const STATUS_OPTIONS: (AppealStatus | "all")[] = [
  "all",
  "pending",
  "under_review",
  "upheld",
  "overturned",
];

const STATUS_LABELS: Record<AppealStatus, string> = {
  pending: "Pending review",
  under_review: "Under review",
  upheld: "Upheld",
  overturned: "Overturned",
};

export default function AppealsPage() {
  const [items, setItems] = useState<AppealQueueItem[]>([]);
  const [filter, setFilter] = useState<AppealStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [resolver, setResolver] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAppeals(filter === "all" ? undefined : filter);
      setItems(data.appeals);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not load the appeal queue."
      );
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleResolve(
    item: AppealQueueItem,
    status: "upheld" | "overturned"
  ) {
    if (notes.trim().length < 10) {
      setError("Please add at least 10 characters of evaluator notes.");
      return;
    }
    if (!resolver.trim()) {
      setError("Please enter your name or email.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await resolveAppeal(item.id, {
        status,
        evaluator_notes: notes.trim(),
        resolved_by: resolver.trim(),
      });
      setNotice(
        `${item.submission?.team_name ?? "Submission"} appeal ${status}.`
      );
      setNotes("");
      setExpanded(null);
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not resolve the appeal."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wide">
      <NavLinks />
      <h1>Appeals queue</h1>
      <p className="subtitle">
        Review contested results with the original AI scores and feedback
        attached.
      </p>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && <p className="success">{notice}</p>}

      <div className="inline-controls">
        <label htmlFor="appeal-filter">Status</label>
        <select
          id="appeal-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value as AppealStatus | "all")}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "All" : STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="hint">Loading appeals…</p>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon" aria-hidden="true">
            📭
          </div>
          <h3>No appeals here</h3>
          <p>Nothing matches this filter right now.</p>
        </div>
      ) : (
        <div className="appeal-list">
          {items.map((item) => (
            <div className="card appeal-item" key={item.id}>
              <div className="appeal-item-header">
                <div>
                  <strong>
                    {item.submission?.team_name ?? "Unknown team"}
                  </strong>
                  <span className="meta"> · {STATUS_LABELS[item.status]}</span>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() =>
                    setExpanded(expanded === item.id ? null : item.id)
                  }
                >
                  {expanded === item.id ? "Collapse" : "Review"}
                </button>
              </div>
              <p className="appeal-text">{item.appeal_text}</p>
              {expanded === item.id && (
                <div className="appeal-detail">
                  <h4>Original scores</h4>
                  <table className="scores">
                    <thead>
                      <tr>
                        <th>Criterion</th>
                        <th>Score</th>
                        <th>Justification</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(item.scores ?? []).map((s) => (
                        <tr key={s.criterion}>
                          <td>{s.criterion.replace(/_/g, " ")}</td>
                          <td>{s.score}</td>
                          <td>{s.justification}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {item.feedback && (
                    <div className="feedback-card">
                      <h4>Feedback</h4>
                      <p>
                        <span
                          className={`badge ${
                            item.feedback.verdict === "shortlist"
                              ? "badge-shortlist"
                              : "badge-reject"
                          }`}
                        >
                          {item.feedback.verdict}
                        </span>
                      </p>
                      <ul>
                        {(item.feedback.strengths ?? []).map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {item.status === "pending" ||
                  item.status === "under_review" ? (
                    <div className="resolve-form">
                      <h4>Resolve</h4>
                      <label htmlFor={`notes-${item.id}`}>
                        Evaluator notes
                      </label>
                      <textarea
                        id={`notes-${item.id}`}
                        rows={3}
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Your assessment of the appeal…"
                      />
                      <label htmlFor={`resolver-${item.id}`}>
                        Your name or email
                      </label>
                      <input
                        id={`resolver-${item.id}`}
                        type="text"
                        value={resolver}
                        onChange={(e) => setResolver(e.target.value)}
                        placeholder="alice@example.com"
                      />
                      <div className="modal-actions">
                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={busy}
                          onClick={() => handleResolve(item, "overturned")}
                        >
                          Overturn
                        </button>
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busy}
                          onClick={() => handleResolve(item, "upheld")}
                        >
                          Uphold
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="hint">
                      Resolved by {item.resolved_by ?? "unknown"} —{" "}
                      {item.evaluator_notes ?? "no notes"}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
