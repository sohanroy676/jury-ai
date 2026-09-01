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
      // The panel stays usable without the appeal state (e.g. backend
      // briefly down); a silent null beats blocking the form.
      setAppeal(null);
    }
  }, [submissionId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Results must be published before an appeal can be filed.
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
        <h2>Appeal</h2>
        <p className="hint">
          Appeals open once your results are published (after feedback is
          generated).
        </p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Appeal</h2>
      {appeal ? (
        <div className="appeal-status">
          <p>
            <span className={`badge badge-${appeal.status}`}>
              {STATUS_LABELS[appeal.status]}
            </span>
          </p>
          <p className="appeal-text">{appeal.appeal_text}</p>
          {appeal.evaluator_notes && (
            <p className="appeal-notes">
              <strong>Evaluator notes:</strong> {appeal.evaluator_notes}
            </p>
          )}
          {appeal.resolved_at && (
            <p className="hint">Resolved {appeal.resolved_at}</p>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <label htmlFor="appeal-text">
            Why should this result be reconsidered? (min {MIN_APPEAL_LENGTH}{" "}
            characters)
          </label>
          <textarea
            id="appeal-text"
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Explain what you believe was misjudged and why…"
          />
          <span
            className={`char-count${
              text.trim().length >= MIN_APPEAL_LENGTH ? " char-count--ok" : ""
            }`}
          >
            {text.trim().length} / {MIN_APPEAL_LENGTH} min characters
          </span>
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
          {notice && <p className="success">{notice}</p>}
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || text.trim().length < MIN_APPEAL_LENGTH}
          >
            {submitting ? "Filing…" : "File appeal"}
          </button>
        </form>
      )}
    </section>
  );
}
