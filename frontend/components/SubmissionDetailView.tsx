"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AppealPanel from "./AppealPanel";
import ErrorBanner from "./ErrorBanner";
import NavLinks from "./NavLinks";
import StageTracker from "./StageTracker";
import {
  ApiError,
  CRITERIA,
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

  // v1.1.0 near-real-time status: poll while the submission has not yet
  // reached a final verdict. A busy-guard prevents overlapping refreshes;
  // the interval is cleaned up on unmount or once the verdict lands.
  const pollBusy = useRef(false);
  const quietLoad = useCallback(async () => {
    if (pollBusy.current) return;
    pollBusy.current = true;
    try {
      await load();
    } finally {
      pollBusy.current = false;
    }
  }, [load]);

  const verdict = feedback?.verdict ?? null;
  useEffect(() => {
    if (verdict) return;
    const id = window.setInterval(() => {
      void quietLoad();
    }, 10_000);
    return () => window.clearInterval(id);
  }, [quietLoad, verdict]);

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

      <StageTracker
        state={{
          parsed: detail?.parsed != null,
          scored:
            Array.isArray(scores) &&
            scores.length > 0 &&
            CRITERIA.every((criterion) =>
              scores.some((row) => row.criterion === criterion)
            ),
          verdict,
        }}
      />

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
                  <td>
                    <strong>{s.score}</strong>
                    {s.overridden_at != null &&
                      typeof s.original_score === "number" && (
                        <span
                          className="override-meta"
                          title={`AI originally scored ${s.original_score}`}
                        >
                          <br />
                          <span className="badge badge-tie">
                            was {s.original_score} (AI)
                          </span>
                        </span>
                      )}
                  </td>
                  <td>
                    {s.justification}
                    {s.cited_excerpt ? (
                      <blockquote className="citation">
                        {s.cited_excerpt}
                      </blockquote>
                    ) : (
                      <blockquote className="citation citation--empty">
                        No citation provided for this score.
                      </blockquote>
                    )}
                    {s.overridden_by && (
                      <p className="override-provenance">
                        Overridden by <strong>{s.overridden_by}</strong>
                        {s.override_reason ? `: “${s.override_reason}”` : ""}
                      </p>
                    )}
                  </td>
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

      <AppealPanel submissionId={submissionId} feedback={feedback} />

      {detail?.flagged_images && detail.flagged_images.length > 0 && (
        <section className="card">
          <h2>
            Images flagged for review{" "}
            <span className="badge badge-tie">
              {detail.flagged_images.length}
            </span>
          </h2>
          <p className="hint">
            The vision router could not confidently classify or describe these
            images. Please verify them manually.
          </p>
          <div className="review-queue">
            {detail.flagged_images.map((img, i) => (
              <div className="review-card" key={i}>
                <div className="review-meta">
                  <span className="badge badge-tie">needs review</span>
                  {img.page != null && <span>page {img.page}</span>}
                  {img.slide != null && <span>slide {img.slide}</span>}
                  {img.classification && (
                    <span>guessed: {img.classification}</span>
                  )}
                  {typeof img.confidence === "number" && (
                    <span>{Math.round(img.confidence * 100)}% confidence</span>
                  )}
                </div>
                <p className="review-description">
                  {img.description || (
                    <em>No description was generated for this image.</em>
                  )}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <h2>Parsed text</h2>
        {detail?.parsed?.raw_text ? (
          <>
            <pre className="parsed-text">{detail.parsed.raw_text}</pre>
            <a
              className="button-link"
              href={exportPdfUrl(submissionId, {
                topN: Number(topNInput) || undefined,
              })}
            >
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
