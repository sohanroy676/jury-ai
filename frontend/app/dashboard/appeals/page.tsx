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

      <section className="card" style={{ padding: "1.75rem 2rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                fontSize: "0.75rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "#a5b4fc",
                marginBottom: "0.35rem",
              }}
            >
              <span>⚖️ Evaluator Appeals Portal</span>
            </div>
            <h1>Appeals Queue</h1>
            <p className="subtitle" style={{ margin: 0 }}>
              Review contested submission results with complete AI score breakdowns and evidence citations.
            </p>
          </div>
          <div className="inline-controls" style={{ margin: 0 }}>
            <label htmlFor="appeal-filter">Filter Status:</label>
            <select
              id="appeal-filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value as AppealStatus | "all")}
              style={{ width: "160px" }}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === "all" ? "All Appeals" : STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="alert alert--success" style={{ marginBottom: "1.5rem" }}>
          <span>{notice}</span>
        </div>
      )}

      {loading ? (
        <p className="hint" style={{ textAlign: "center", padding: "2rem" }}>Loading appeals queue…</p>
      ) : items.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem 1.5rem", color: "#94a3b8" }}>
          <p style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>📭</p>
          <h3>No appeals found</h3>
          <p className="hint">No submission appeals match the selected filter status.</p>
        </div>
      ) : (
        <div className="appeal-list" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {items.map((item) => (
            <div className="card appeal-item" key={item.id} style={{ margin: 0 }}>
              <div className="card__header" style={{ marginBottom: "0.75rem" }}>
                <div>
                  <h3 style={{ fontSize: "1.15rem", display: "inline-block", marginRight: "0.75rem" }}>
                    {item.submission?.team_name ?? "Unknown Team"}
                  </h3>
                  <span className={`badge badge--${item.status === "upheld" ? "shortlist" : item.status === "overturned" ? "reject" : "tie"}`}>
                    {STATUS_LABELS[item.status]}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() =>
                    setExpanded(expanded === item.id ? null : item.id)
                  }
                >
                  {expanded === item.id ? "Hide Details ▲" : "Review Appeal ▼"}
                </button>
              </div>

              <div
                style={{
                  background: "rgba(15, 23, 42, 0.6)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "10px",
                  padding: "1rem",
                  marginBottom: expanded === item.id ? "1.25rem" : 0,
                }}
              >
                <p style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#a5b4fc", fontWeight: 600, marginBottom: "0.35rem" }}>
                  Team Appeal Statement
                </p>
                <p className="appeal-text" style={{ fontSize: "0.925rem", color: "#f8fafc", margin: 0 }}>
                  “{item.appeal_text}”
                </p>
              </div>

              {expanded === item.id && (
                <div className="appeal-detail" style={{ paddingTop: "0.5rem" }}>
                  <h4 style={{ fontSize: "0.95rem", color: "#94a3b8", marginBottom: "0.75rem" }}>
                    Original Criterion Breakdown
                  </h4>
                  <div className="table-container" style={{ marginBottom: "1.25rem" }}>
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
                            <td style={{ textTransform: "capitalize", fontWeight: 600 }}>
                              {s.criterion.replace(/_/g, " ")}
                            </td>
                            <td>
                              <span style={{ color: "#818cf8", fontWeight: 700 }}>{s.score}</span>
                            </td>
                            <td>{s.justification}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {item.feedback && (
                    <div className="feedback-card" style={{ marginBottom: "1.25rem" }}>
                      <h4 style={{ fontSize: "0.95rem", color: "#94a3b8", marginBottom: "0.5rem" }}>
                        Generated Written Feedback
                      </h4>
                      <p style={{ marginBottom: "0.5rem" }}>
                        <span
                          className={`badge ${
                            item.feedback.verdict === "shortlist"
                              ? "badge--shortlist"
                              : "badge--reject"
                          }`}
                        >
                          Verdict: {item.feedback.verdict?.toUpperCase()}
                        </span>
                      </p>
                      <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
                        {(item.feedback.strengths ?? []).map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {item.status === "pending" || item.status === "under_review" ? (
                    <div
                      style={{
                        background: "rgba(30, 41, 59, 0.5)",
                        border: "1px solid rgba(255, 255, 255, 0.12)",
                        borderRadius: "12px",
                        padding: "1.25rem",
                      }}
                    >
                      <h4 style={{ fontSize: "1rem", marginBottom: "1rem", color: "#ffffff" }}>
                        Evaluator Adjudication Form
                      </h4>

                      <div className="form-group">
                        <label htmlFor={`notes-${item.id}`}>Evaluator Decision Notes</label>
                        <textarea
                          id={`notes-${item.id}`}
                          rows={3}
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          placeholder="Provide detailed justification for upholding or overturning this appeal..."
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor={`resolver-${item.id}`}>Evaluator Identity</label>
                        <input
                          id={`resolver-${item.id}`}
                          type="text"
                          value={resolver}
                          onChange={(e) => setResolver(e.target.value)}
                          placeholder="evaluator@hackathon.org"
                        />
                      </div>

                      <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end", marginTop: "1.25rem" }}>
                        <button
                          type="button"
                          className="btn btn--danger"
                          disabled={busy}
                          onClick={() => handleResolve(item, "overturned")}
                        >
                          Overturn Appeal
                        </button>
                        <button
                          type="button"
                          className="btn btn--primary"
                          disabled={busy}
                          onClick={() => handleResolve(item, "upheld")}
                        >
                          Uphold Appeal
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="hint" style={{ background: "rgba(15,23,42,0.6)", padding: "0.75rem", borderRadius: "8px" }}>
                      Resolved by <strong>{item.resolved_by ?? "unknown"}</strong> —{" "}
                      <em>{item.evaluator_notes ?? "no notes provided"}</em>
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
