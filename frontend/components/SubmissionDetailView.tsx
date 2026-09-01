"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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

  const fetchData = useCallback(
    async (showLoadingIndicator: boolean) => {
      if (showLoadingIndicator) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await fetchSubmission(submissionId);
        setDetail(data);
        const fb = await fetchFeedback(submissionId);
        setFeedback(fb.feedback);
      } catch (err) {
        if (showLoadingIndicator) {
          setError(
            err instanceof ApiError
              ? err.message
              : "Unexpected error loading this submission."
          );
        }
      } finally {
        if (showLoadingIndicator) {
          setLoading(false);
        }
      }
    },
    [submissionId]
  );

  const load = useCallback(() => fetchData(true), [fetchData]);

  useEffect(() => {
    void load();
  }, [load]);

  const pollBusy = useRef(false);
  const quietLoad = useCallback(async () => {
    if (pollBusy.current) return;
    pollBusy.current = true;
    try {
      await fetchData(false);
    } finally {
      pollBusy.current = false;
    }
  }, [fetchData]);

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

  const uniqueScores = useMemo(() => {
    const raw = detail?.scores ?? [];
    const map = new Map<string, (typeof raw)[0]>();
    for (const s of raw) {
      if (!map.has(s.criterion)) {
        map.set(s.criterion, s);
      }
    }
    return Array.from(map.values());
  }, [detail?.scores]);

  if (loading)
    return (
      <main className="wide">
        <NavLinks />
        <p className="hint">Loading submission record…</p>
      </main>
    );

  const submission = detail?.submission ?? null;

  return (
    <main className="wide">
      <NavLinks />

      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h1>{submission ? submission.team_name : "Submission Record"}</h1>
            {submission && (
              <p className="meta" style={{ margin: "0.25rem 0 0.75rem" }}>
                Format: <strong>{submission.file_type?.toUpperCase() || "PDF"}</strong>
                {submission.uploaded_at && ` · Uploaded ${new Date(submission.uploaded_at).toLocaleString()}`}
                {submission.status && ` · Status: ${submission.status}`}
              </p>
            )}
          </div>
          {submission?.id && (
            <a
              className="btn btn--secondary btn--sm"
              href={exportPdfUrl(submissionId, {
                topN: Number(topNInput) || undefined,
              })}
            >
              📄 Download PDF Report
            </a>
          )}
        </div>

        <div style={{ marginTop: "1rem" }}>
          <StageTracker
            state={{
              parsed: detail?.parsed != null,
              scored:
                Array.isArray(uniqueScores) &&
                uniqueScores.length > 0 &&
                CRITERIA.every((criterion) =>
                  uniqueScores.some((row) => row.criterion === criterion)
                ),
              verdict,
            }}
          />
        </div>
      </section>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="alert alert--success" style={{ marginBottom: "1rem" }}>
          <span>{notice}</span>
        </div>
      )}

      <section className="card">
        <h2 className="card__title" style={{ marginBottom: "1rem" }}>
          Scoring & Feedback Controls
        </h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleScore}
            disabled={scoring}
          >
            {scoring ? "Scoring…" : "Score this submission"}
          </button>
        </div>

        <div className="inline-controls" style={{ marginBottom: "1.5rem" }}>
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
            className="btn btn--secondary"
            onClick={handleGenerateFeedback}
            disabled={generating}
          >
            {generating ? "Generating…" : "Generate feedback"}
          </button>
        </div>

        <h3 style={{ marginBottom: "1rem" }}>Criterion scores</h3>
        {uniqueScores.length > 0 ? (
          <div className="table-container" style={{ marginBottom: "1.5rem" }}>
            <table className="scores">
              <thead>
                <tr>
                  <th>Criterion</th>
                  <th style={{ width: "120px" }}>Score</th>
                  <th>Justification</th>
                </tr>
              </thead>
              <tbody>
                {uniqueScores.map((s) => (
                  <tr key={s.criterion}>
                    <td style={{ textTransform: "capitalize", fontWeight: 600 }}>
                      {s.criterion.replace(/_/g, " ")}
                    </td>
                    <td>
                      <div className="score-bar">
                        <span className="score-bar__value" style={{ fontSize: "1.1rem", fontWeight: 700 }}>
                          {s.score}
                        </span>
                        <div className="score-bar__track" style={{ width: "60px" }}>
                          <div
                            className={`score-bar__fill ${
                              s.score >= 8
                                ? "score-bar__fill--high"
                                : s.score >= 5
                                ? "score-bar__fill--medium"
                                : "score-bar__fill--low"
                            }`}
                            style={{ width: `${s.score * 10}%` }}
                          />
                        </div>
                      </div>
                      {s.overridden_at != null &&
                        typeof s.original_score === "number" && (
                          <div className="override-meta" style={{ marginTop: "0.25rem" }}>
                            <span className="badge badge--tie">
                              was {s.original_score} (AI)
                            </span>
                          </div>
                        )}
                    </td>
                    <td>
                      <p style={{ margin: 0 }}>{s.justification}</p>
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
                        <p style={{ fontSize: "0.75rem", color: "#c084fc", marginTop: "0.4rem" }}>
                          Overridden by <strong>{s.overridden_by}</strong>
                          {s.override_reason ? `: “${s.override_reason}”` : ""}
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint">Not scored yet.</p>
        )}

        <h3 style={{ marginBottom: "1rem" }}>Feedback</h3>
        {feedback ? (
          <div className="feedback-card">
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
              <span
                className={`badge ${
                  feedback.verdict === "shortlist"
                    ? "badge--shortlist"
                    : "badge--reject"
                }`}
                style={{ fontSize: "0.85rem", padding: "0.35rem 0.85rem" }}
              >
                {feedback.verdict}
              </span>
              {feedback.agent_version && (
                <span className="hint"> · agent {feedback.agent_version}</span>
              )}
            </div>
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
            <p style={{ color: "#e2e8f0", background: "rgba(15,23,42,0.5)", padding: "0.75rem", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.08)" }}>
              {feedback.suggestion}
            </p>
          </div>
        ) : (
          <p className="hint">No feedback generated yet.</p>
        )}
      </section>

      <AppealPanel submissionId={submissionId} feedback={feedback} />

      {detail?.flagged_images && detail.flagged_images.length > 0 && (
        <section className="card">
          <h2 className="card__title" style={{ marginBottom: "0.75rem" }}>
            Images flagged for review{" "}
            <span className="badge badge--tie" style={{ marginLeft: "0.5rem" }}>
              {detail.flagged_images.length}
            </span>
          </h2>
          <p className="hint" style={{ marginBottom: "1rem" }}>
            The vision router could not confidently classify or describe these images. Please verify them manually.
          </p>
          <div className="review-queue">
            {detail.flagged_images.map((img, i) => (
              <div className="card" key={i} style={{ background: "rgba(15,23,42,0.5)", marginBottom: "0.75rem" }}>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
                  <span className="badge badge--tie">needs review</span>
                  {img.page != null && <span className="badge">page {img.page}</span>}
                  {img.slide != null && <span className="badge">slide {img.slide}</span>}
                  {img.classification && (
                    <span className="badge badge--ai">type: {img.classification}</span>
                  )}
                  {typeof img.confidence === "number" && (
                    <span className="badge">{Math.round(img.confidence * 100)}% confidence</span>
                  )}
                </div>
                <p className="review-description" style={{ fontSize: "0.875rem", margin: 0 }}>
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
        <h2 className="card__title" style={{ marginBottom: "1rem" }}>Parsed text</h2>
        {detail?.parsed?.raw_text ? (
          <>
            <pre className="parsed-text">{detail.parsed.raw_text}</pre>
            <div style={{ marginTop: "1rem" }}>
              <a
                className="button-link btn btn--secondary"
                href={exportPdfUrl(submissionId, {
                  topN: Number(topNInput) || undefined,
                })}
              >
                Download PDF report
              </a>
            </div>
          </>
        ) : (
          <p className="hint">No parsed text stored for this submission.</p>
        )}
      </section>
    </main>
  );
}
