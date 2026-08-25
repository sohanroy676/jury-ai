"use client";

import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "./ErrorBanner";
import NavLinks from "./NavLinks";
import {
  ApiError,
  FeedbackRecord,
  SubmissionDetail,
  exportPdfUrl,
  fetchFeedback,
  fetchSubmission,
  triggerFeedback,
  triggerScore,
} from "../lib/api";

export default function SubmissionDetailView({
  submissionId,
}: {
  submissionId: string;
}) {
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [feedback, setFeedback] = useState<FeedbackRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [scoring, setScoring] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [topNInput, setTopNInput] = useState("5");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSubmission(submissionId);
      setDetail(data);
      const fb = await fetchFeedback(submissionId);
      setFeedback(fb.feedback);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Unexpected error loading this submission."
      );
    } finally {
      setLoading(false);
    }
  }, [submissionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleScore() {
    setScoring(true);
    setError(null);
    setNotice(null);
    try {
      const result = await triggerScore(submissionId);
      setNotice(`Scored by agent ${result.agent_version}.`);
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Scoring failed unexpectedly."
      );
    } finally {
      setScoring(false);
    }
  }

  async function handleGenerateFeedback() {
    const topN = Number(topNInput);
    if (!Number.isInteger(topN) || topN < 1) {
      setError("top N must be a positive whole number.");
      return;
    }
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const result = await triggerFeedback(submissionId, { topN });
      setFeedback(result);
      setNotice(
        `Feedback generated (verdict: ${result.verdict}, shortlist cutoff top ${topN}).`
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Feedback generation failed unexpectedly."
      );
    } finally {
      setGenerating(false);
    }
  }

  if (loading)
    return (
      <main>
        <NavLinks />
        <p>Loading submission…</p>
      </main>
    );

  const submission = detail?.submission ?? null;
  const scores = detail?.scores ?? [];

  return (
    <main>
      <NavLinks />
      <h1>{submission ? submission.team_name : "Submission"}</h1>
      {submission && (
        <p className="meta">
          {submission.file_type?.toUpperCase() || "unknown type"}
          {submission.uploaded_at && ` · uploaded ${submission.uploaded_at}`}
          {submission.status && ` · status: ${submission.status}`}
        </p>
      )}

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && <p className="success">{notice}</p>}

      <section className="card">
        <h2>Scoring & feedback</h2>
        <div className="inline-controls">
          <button type="button" onClick={handleScore} disabled={scoring}>
            {scoring ? "Scoring…" : "Score this submission"}
          </button>
        </div>
        <div className="inline-controls">
          <label htmlFor="feedback-top-n">Shortlist cutoff top N</label>
          <input
            id="feedback-top-n"
            type="number"
            min={1}
            value={topNInput}
            onChange={(e) => setTopNInput(e.target.value)}
          />
          <button
            type="button"
            onClick={handleGenerateFeedback}
            disabled={generating}
          >
            {generating ? "Generating…" : "Generate feedback"}
          </button>
        </div>

        <h3>Criterion scores</h3>
        {scores.length > 0 ? (
          <table className="scores">
            <thead>
              <tr>
                <th>Criterion</th>
                <th>Score</th>
                <th>Justification</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s) => (
                <tr key={s.criterion}>
                  <td>{s.criterion.replace(/_/g, " ")}</td>
                  <td>{s.score}</td>
                  <td>{s.justification}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="hint">Not scored yet.</p>
        )}

        <h3>Feedback</h3>
        {feedback ? (
          <div className="feedback-card">
            <p>
              <span
                className={`badge ${
                  feedback.verdict === "shortlist"
                    ? "badge-shortlist"
                    : "badge-reject"
                }`}
              >
                {feedback.verdict}
              </span>
              {feedback.agent_version && (
                <span className="meta"> · agent {feedback.agent_version}</span>
              )}
            </p>
            <h4>Strengths</h4>
            <ul>
              {(feedback.strengths ?? []).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
            <h4>Weaknesses</h4>
            <ul>
              {(feedback.weaknesses ?? []).map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
            <h4>Suggested next step</h4>
            <p>{feedback.suggestion}</p>
          </div>
        ) : (
          <p className="hint">No feedback generated yet.</p>
        )}
      </section>

      <section className="card">
        <h2>Parsed text</h2>
        {detail?.parsed?.raw_text ? (
          <>
            <pre className="parsed-text">{detail.parsed.raw_text}</pre>
            <a className="button-link" href={exportPdfUrl(submissionId)}>
              Download PDF report
            </a>
          </>
        ) : (
          <p className="hint">No parsed text stored for this submission.</p>
        )}
      </section>
    </main>
  );
}
