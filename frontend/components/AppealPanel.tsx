"use client";

import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "./ErrorBanner";
import {
  ApiError,
  Appeal,
  AppealStatus,
  FeedbackRecord,
  fetchAppeal,
  fileAppeal,
} from "../lib/api";

const MIN_APPEAL_LENGTH = 50;

const STATUS_LABELS: Record<AppealStatus, string> = {
  pending: "Pending review",
  under_review: "Under review",
  upheld: "Upheld",
  overturned: "Overturned",
};

export default function AppealPanel({
  submissionId,
  feedback,
}: {
  submissionId: string;
  feedback: FeedbackRecord | null;
}) {
  const [appeal, setAppeal] = useState<Appeal | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchAppeal(submissionId);
      setAppeal(data.appeal);
    } catch {
      setAppeal(null);
    }
  }, [submissionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const resultsPublished = feedback != null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (text.trim().length < MIN_APPEAL_LENGTH) {
      setError(
        `Please write at least ${MIN_APPEAL_LENGTH} characters explaining your appeal.`
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const created = await fileAppeal(submissionId, text.trim());
      setAppeal(created as Appeal);
      setText("");
      setNotice("Appeal filed — an evaluator will review it.");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not file the appeal."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (!resultsPublished) {
    return (
      <section className="card">
        <h2 className="card__title" style={{ marginBottom: "0.5rem" }}>Contest Results (Appeal)</h2>
        <p className="hint">
          Appeals open automatically once official written feedback is published for your team.
        </p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2 className="card__title" style={{ marginBottom: "1rem" }}>Contest Results (Appeal)</h2>
      {appeal ? (
        <div className="appeal-status">
          <div style={{ marginBottom: "0.75rem" }}>
            <span className={`badge badge--${appeal.status === "upheld" ? "shortlist" : appeal.status === "overturned" ? "reject" : "tie"}`}>
              Status: {STATUS_LABELS[appeal.status]}
            </span>
          </div>
          <div style={{ background: "rgba(15,23,42,0.6)", padding: "1rem", borderRadius: "10px", border: "1px solid rgba(255,255,255,0.08)", marginBottom: "0.75rem" }}>
            <p className="appeal-text" style={{ fontSize: "0.925rem", margin: 0 }}>“{appeal.appeal_text}”</p>
          </div>
          {appeal.evaluator_notes && (
            <p className="appeal-notes" style={{ fontSize: "0.875rem", color: "#c084fc", margin: "0.5rem 0" }}>
              <strong>Evaluator Resolution Notes:</strong> {appeal.evaluator_notes}
            </p>
          )}
          {appeal.resolved_at && (
            <p className="hint">Resolved on {new Date(appeal.resolved_at).toLocaleString()}</p>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="appeal-text">
              Explain why this evaluation should be reconsidered (min {MIN_APPEAL_LENGTH} characters)
            </label>
            <textarea
              id="appeal-text"
              rows={4}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Cite specific pitch deck sections or working prototype capabilities that were misjudged..."
            />
            <span
              style={{
                fontSize: "0.75rem",
                color: text.trim().length >= MIN_APPEAL_LENGTH ? "#34d399" : "#94a3b8",
                textAlign: "right",
              }}
            >
              {text.trim().length} / {MIN_APPEAL_LENGTH} min characters
            </span>
          </div>

          <ErrorBanner message={error} onDismiss={() => setError(null)} />
          {notice && (
            <div className="alert alert--success" style={{ marginBottom: "1rem" }}>
              <span>{notice}</span>
            </div>
          )}

          <button
            type="submit"
            className="btn btn--primary"
            disabled={submitting || text.trim().length < MIN_APPEAL_LENGTH}
          >
            {submitting ? "Filing Appeal…" : "File Appeal →"}
          </button>
        </form>
      )}
    </section>
  );
}
