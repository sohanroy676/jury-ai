"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import ErrorBanner from "../../components/ErrorBanner";
import NavLinks from "../../components/NavLinks";
import TrackSelector from "../../components/TrackSelector";
import {
  ApiError,
  BatchFeedbackResult,
  BatchScoreResult,
  CRITERIA,
  Criterion,
  Leaderboard,
  exportCsvUrl,
  fetchRankings,
  generatePendingFeedback,
  overrideScore,
  saveRubric,
  scorePending,
} from "../../lib/api";
import type { RankedRow, Weights } from "../../lib/api";

const MIN_OVERRIDE_REASON = 10;
const PAGE_SIZES = [25, 50, 100] as const;

type WeightInputs = Record<Criterion, string>;

const INITIAL_WEIGHT_INPUTS: WeightInputs = {
  problem_fit: "25",
  technical_depth: "25",
  feasibility: "25",
  innovation: "25",
};

interface OverrideTarget {
  submissionId: string;
  teamName: string;
  criterion: Criterion;
  current: number;
}

export default function DashboardPage() {
  const [selectedTrack, setSelectedTrack] = useState<string>("default");
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [loadingBoard, setLoadingBoard] = useState(true);
  const [boardError, setBoardError] = useState<string | null>(null);

  const [weightInputs, setWeightInputs] = useState<WeightInputs>(
    INITIAL_WEIGHT_INPUTS
  );
  const [savingRubric, setSavingRubric] = useState(false);

  const [topNInput, setTopNInput] = useState("5");
  const [appliedTopN, setAppliedTopN] = useState<number | undefined>(undefined);

  const [batchLimitInput, setBatchLimitInput] = useState("10");
  const [batching, setBatching] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchScoreResult | null>(null);

  const [fbLimitInput, setFbLimitInput] = useState("10");
  const [generating, setGenerating] = useState(false);
  const [fbResult, setFbResult] = useState<BatchFeedbackResult | null>(null);

  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(25);
  const [overrideTarget, setOverrideTarget] = useState<OverrideTarget | null>(
    null
  );
  const [overrideScoreInput, setOverrideScoreInput] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideEvaluator, setOverrideEvaluator] = useState("");
  const [savingOverride, setSavingOverride] = useState(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const id = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(id);
  }, [notice]);

  const load = useCallback(async () => {
    setLoadingBoard(true);
    setBoardError(null);
    try {
      const data = await fetchRankings(selectedTrack, { topN: appliedTopN });
      setBoard(data);
    } catch (err) {
      setBoardError(
        err instanceof ApiError
          ? err.message
          : "Unexpected error loading rankings."
      );
    } finally {
      setLoadingBoard(false);
    }
  }, [selectedTrack, appliedTopN]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSaveRubric(e: React.FormEvent) {
    e.preventDefault();
    const parsed = Object.fromEntries(
      CRITERIA.map((c) => [c, Number(weightInputs[c])])
    ) as Weights;
    if (CRITERIA.some((c) => !Number.isFinite(parsed[c]) || parsed[c] < 0)) {
      setBoardError("Weights must be non-negative numbers.");
      return;
    }
    const sum = CRITERIA.reduce((acc, c) => acc + parsed[c], 0);
    if (Math.abs(sum - 100) > 0.01 && Math.abs(sum - 1) > 0.0001) {
      setBoardError("Weights must sum to 100 (percent) or 1 (fractions).");
      return;
    }

    setSavingRubric(true);
    setBoardError(null);
    try {
      await saveRubric(selectedTrack, parsed);
      await load();
      setNotice("Rubric saved — rankings reweighted.");
    } catch (err) {
      setBoardError(
        err instanceof ApiError ? err.message : "Could not save the rubric."
      );
    } finally {
      setSavingRubric(false);
    }
  }

  async function handleApplyTopN(e: React.FormEvent) {
    e.preventDefault();
    const parsed = Number(topNInput);
    if (!Number.isInteger(parsed) || parsed < 1) {
      setBoardError("top N must be a positive whole number.");
      return;
    }
    setAppliedTopN(parsed);
  }

  async function handleBatchScore() {
    const limit = Number(batchLimitInput);
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      setBoardError("Batch size must be a whole number between 1 and 50.");
      return;
    }
    setBatching(true);
    setBatchResult(null);
    setBoardError(null);
    try {
      const result = await scorePending(limit);
      setBatchResult(result);
      await load();
    } catch (err) {
      setBoardError(
        err instanceof ApiError ? err.message : "Batch scoring failed."
      );
    } finally {
      setBatching(false);
    }
  }

  async function handleBatchFeedback() {
    const limit = Number(fbLimitInput);
    if (!Number.isInteger(limit) || limit < 1 || limit > 50) {
      setBoardError("Batch size must be a whole number between 1 and 50.");
      return;
    }
    setGenerating(true);
    setFbResult(null);
    setBoardError(null);
    try {
      const result = await generatePendingFeedback(limit, {
        hackathonId: selectedTrack,
        topN: appliedTopN,
      });
      setFbResult(result);
      await load();
    } catch (err) {
      setBoardError(
        err instanceof ApiError ? err.message : "Feedback generation failed."
      );
    } finally {
      setGenerating(false);
    }
  }

  function openOverride(row: RankedRow, criterion: Criterion) {
    const current = row.criterion_scores[criterion];
    if (typeof current !== "number") return;
    setOverrideTarget({
      submissionId: row.submission_id,
      teamName: row.team_name,
      criterion,
      current,
    });
    setOverrideScoreInput(String(current));
    setOverrideReason("");
    setOverrideEvaluator("");
    setOverrideError(null);
  }

  function closeOverride() {
    setOverrideTarget(null);
    setOverrideError(null);
  }

  const overrideReasonValid =
    overrideReason.trim().length >= MIN_OVERRIDE_REASON;
  const overrideScoreValid = Number.isInteger(Number(overrideScoreInput))
    ? Number(overrideScoreInput) >= 1 && Number(overrideScoreInput) <= 10
    : false;
  const overrideEvaluatorValid = overrideEvaluator.trim().length > 0;

  async function handleOverrideSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!overrideTarget) return;
    if (
      !overrideScoreValid ||
      !overrideReasonValid ||
      !overrideEvaluatorValid
    ) {
      setOverrideError(
        `Score must be a whole number 1-10, the reason needs at least ${MIN_OVERRIDE_REASON} characters, and an evaluator name is required.`
      );
      return;
    }
    setSavingOverride(true);
    setOverrideError(null);
    try {
      const result = await overrideScore(
        overrideTarget.submissionId,
        overrideTarget.criterion,
        {
          score: Number(overrideScoreInput),
          reason: overrideReason.trim(),
          evaluator: overrideEvaluator.trim(),
        }
      );
      const ctx = result.rank_context;
      setNotice(
        `${overrideTarget.teamName}'s ${overrideTarget.criterion.replace(
          /_/g,
          " "
        )} overridden to ${result.updated_score.score}` +
          (typeof ctx?.rank === "number"
            ? ` — now rank ${ctx.rank} (composite ${(
                ctx.composite_score ?? 0
              ).toFixed(2)}).`
            : ".")
      );
      closeOverride();
      await load();
    } catch (err) {
      setOverrideError(
        err instanceof ApiError ? err.message : "Override failed unexpectedly."
      );
    } finally {
      setSavingOverride(false);
    }
  }

  const totalRows = board?.ranked.length ?? 0;
  const pageCount = Math.max(Math.ceil(totalRows / pageSize), 1);
  const safePage = Math.min(page, pageCount - 1);
  const pagedRows = useMemo(
    () =>
      board?.ranked.slice(safePage * pageSize, (safePage + 1) * pageSize) ?? [],
    [board, safePage, pageSize]
  );

  function handlePageSizeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = Number(e.target.value);
    setPageSize(next);
    setPage(Math.floor((safePage * pageSize) / next));
  }

  return (
    <main className="wide">
      <NavLinks />

      <header
        className="card"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
          padding: "1.75rem 2rem",
        }}
      >
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
            <span>🏆 Live Evaluation Dashboard</span>
          </div>
          <h1>Evaluator dashboard</h1>
          <p className="subtitle" style={{ margin: "0 0 1rem" }}>
            Ranked leaderboard, rubric weights, and batch scoring across hackathon tracks.
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#cbd5e1" }}>
              Active Track:
            </span>
            <TrackSelector activeTrack={selectedTrack} onChange={setSelectedTrack} />
          </div>
        </div>
        <Link className="btn btn--secondary" href="/">
          ← Upload portal
        </Link>
      </header>

      <ErrorBanner message={boardError} onDismiss={() => setBoardError(null)} />

      {notice && (
        <div className="alert alert--success" role="status" style={{ display: "flex", alignItems: "center" }}>
          <span>{notice}</span>
          <button
            type="button"
            className="alert__dismiss"
            aria-label="Dismiss notification"
            onClick={() => setNotice(null)}
          >
            ×
          </button>
        </div>
      )}

      {board && (
        <>
          <div className="stat-grid" aria-label="Pipeline summary">
            <div className="stat-card">
              <span className="stat-card__value">{board.scored_count}</span>
              <span className="stat-card__label">Scored Teams</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value" style={{ color: "#94a3b8" }}>{board.unscored_count}</span>
              <span className="stat-card__label">Unscored Teams</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value" style={{ color: "#fbbf24" }}>{board.partial_count}</span>
              <span className="stat-card__label">Partial Scores</span>
            </div>
          </div>
          <p className="counts" style={{ marginBottom: "1rem" }}>
            {board.scored_count} scored · {board.unscored_count} unscored ·{" "}
            {board.partial_count} partial
            {board.rubric_source === "fallback" &&
              " · using fallback equal weights (no rubric configured)"}
          </p>
        </>
      )}

      <section className="card">
        <h2 className="card__title" style={{ marginBottom: "1rem" }}>
          Rubric weights (%)
        </h2>
        <form onSubmit={handleSaveRubric}>
          <div className="two-col" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
            {CRITERIA.map((c) => (
              <div key={c} className="form-group" style={{ marginBottom: 0 }}>
                <label htmlFor={`weight-${c}`} style={{ textTransform: "capitalize" }}>
                  {c.replace(/_/g, " ")}
                </label>
                <input
                  id={`weight-${c}`}
                  type="number"
                  min={0}
                  step="any"
                  value={weightInputs[c]}
                  onChange={(e) =>
                    setWeightInputs((prev) => ({ ...prev, [c]: e.target.value }))
                  }
                />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
            <p className="hint" style={{ margin: 0 }}>
              Rankings update immediately after saving.
            </p>
            <button
              className="btn btn--primary"
              type="submit"
              disabled={savingRubric}
            >
              {savingRubric ? "Saving…" : "Save rubric"}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="card__header" style={{ flexWrap: "wrap", gap: "1rem" }}>
          <h2 className="card__title">Leaderboard</h2>
          <form onSubmit={handleApplyTopN} className="inline-controls" style={{ margin: 0 }}>
            <label htmlFor="top-n">Shortlist top</label>
            <input
              id="top-n"
              type="number"
              min={1}
              value={topNInput}
              onChange={(e) => setTopNInput(e.target.value)}
            />
            <button className="btn btn--secondary btn--sm" type="submit">
              Apply
            </button>
            <a
              className="btn btn--secondary btn--sm"
              href={
                appliedTopN !== undefined
                  ? exportCsvUrl(selectedTrack, { topN: appliedTopN })
                  : exportCsvUrl(selectedTrack)
              }
            >
              Export CSV
            </a>
          </form>
        </div>

        {loadingBoard ? (
          <div style={{ textAlign: "center", padding: "3rem 1rem", color: "#94a3b8" }} role="status">
            Loading rankings…
          </div>
        ) : board && board.ranked.length > 0 ? (
          <>
            <div className="table-container">
              <table className="leaderboard">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Team</th>
                    {CRITERIA.map((c) => (
                      <th key={c} style={{ textTransform: "capitalize" }}>
                        {c.replace(/_/g, " ")}
                      </th>
                    ))}
                    <th>Composite</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.map((row) => (
                    <tr key={row.submission_id}>
                      <td>
                        <span className={`rank rank--${row.rank}`}>
                          {row.rank}
                        </span>
                      </td>
                      <td>
                        <a
                          href={`/submissions/${row.submission_id}`}
                          style={{ color: "#f8fafc", fontWeight: 600, textDecoration: "none" }}
                        >
                          {row.team_name}
                        </a>
                      </td>
                      {CRITERIA.map((c) => {
                        const value = row.criterion_scores[c];
                        return (
                          <td key={c}>
                            {typeof value === "number" ? (
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                style={{ width: "100%", justifyContent: "space-between", padding: "0.25rem 0.5rem" }}
                                title={`Override ${c.replace(/_/g, " ")} for ${row.team_name}`}
                                onClick={() => openOverride(row, c)}
                              >
                                <span className="score-bar" style={{ width: "100%" }}>
                                  <span className="score-bar__track">
                                    <span
                                      className={`score-bar__fill ${
                                        value >= 8
                                          ? "score-bar__fill--high"
                                          : value >= 5
                                          ? "score-bar__fill--medium"
                                          : "score-bar__fill--low"
                                      }`}
                                      style={{ width: `${value * 10}%` }}
                                    />
                                  </span>
                                  <span className="score-bar__value">{value}</span>
                                </span>
                              </button>
                            ) : (
                              <span style={{ color: "#64748b" }} aria-label="not scored">
                                —
                              </span>
                            )}
                          </td>
                        );
                      })}
                      <td>
                        <div className="score-bar">
                          <div className="score-bar__track">
                            <div
                              className="score-bar__fill score-bar__fill--high"
                              style={{ width: `${row.composite_score * 10}%` }}
                            />
                          </div>
                          <span className="score-bar__value" style={{ color: "#818cf8", fontWeight: 700 }}>
                            {row.composite_score.toFixed(2)}
                          </span>
                        </div>
                      </td>
                      <td>
                        {row.shortlisted && (
                          <span className="badge badge--shortlist">
                            shortlisted
                          </span>
                        )}
                        {row.tied_on_composite && (
                          <span className="badge badge--tie" title="Tied composite score" style={{ marginLeft: "0.35rem" }}>
                            tie
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="hint" style={{ marginTop: "1rem" }}>
              Click any score to override it — a reason is required and the original AI score is preserved.
            </p>

            {totalRows > pageSize && (
              <nav
                className="pagination"
                aria-label="Leaderboard pages"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginTop: "1.25rem",
                  flexWrap: "wrap",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    aria-label="First page"
                    disabled={safePage === 0}
                    onClick={() => setPage(0)}
                  >
                    «
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    disabled={safePage === 0}
                    onClick={() => setPage(safePage - 1)}
                  >
                    ‹ Prev
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    disabled={safePage >= pageCount - 1}
                    onClick={() => setPage(safePage + 1)}
                  >
                    Next ›
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    aria-label="Last page"
                    disabled={safePage >= pageCount - 1}
                    onClick={() => setPage(pageCount - 1)}
                  >
                    »
                  </button>
                </div>
                <span className="page-indicator" style={{ fontSize: "0.875rem", color: "#94a3b8" }}>
                  Page {safePage + 1} of {pageCount}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <label style={{ fontSize: "0.875rem", color: "#94a3b8" }}>Rows</label>
                  <select
                    value={pageSize}
                    onChange={handlePageSizeChange}
                    style={{ width: "80px", padding: "0.25rem 0.5rem" }}
                  >
                    {PAGE_SIZES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </nav>
            )}
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "3rem 1rem", color: "#94a3b8" }}>
            <p style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>🏆</p>
            <h3>No fully-scored submissions yet</h3>
            <p className="hint">Run batch scoring below to build the leaderboard.</p>
          </div>
        )}
      </section>

      <div className="two-col">
        <section className="card">
          <h2 className="card__title">Batch scoring</h2>
          <p className="hint">
            Score unscored submissions with the four specialist agents.
          </p>
          <form onSubmit={handleBatchScore} className="inline-controls" style={{ marginTop: "1rem" }}>
            <label htmlFor="batch-limit">Batch size</label>
            <input
              id="batch-limit"
              type="number"
              min={1}
              max={50}
              value={batchLimitInput}
              onChange={(e) => setBatchLimitInput(e.target.value)}
            />
            <button
              className="btn btn--primary"
              type="submit"
              disabled={batching}
            >
              {batching ? "Scoring…" : "Start batch scoring"}
            </button>
          </form>
          {batchResult && (
            <div className="batch-result">
              <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                Scored {batchResult.scored}, failed {batchResult.failed},{" "}
                {batchResult.remaining} remaining.
              </p>
              <ul style={{ paddingLeft: "1.25rem", margin: 0 }}>
                {batchResult.results.map((r) => (
                  <li key={r.submission_id} style={{ color: r.ok ? "#34d399" : "#fb7185" }}>
                    {r.team_name}: {r.ok ? "scored" : r.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="card">
          <h2 className="card__title">Batch feedback</h2>
          <p className="hint">
            Generate written feedback for teams that do not have it yet.
          </p>
          <form onSubmit={handleBatchFeedback} className="inline-controls" style={{ marginTop: "1rem" }}>
            <label htmlFor="fb-limit">Batch size</label>
            <input
              id="fb-limit"
              type="number"
              min={1}
              max={50}
              value={fbLimitInput}
              onChange={(e) => setFbLimitInput(e.target.value)}
            />
            <button
              className="btn btn--primary"
              type="submit"
              disabled={generating}
            >
              {generating ? "Generating…" : "Start feedback generation"}
            </button>
          </form>
          {fbResult && (
            <div className="batch-result">
              <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                Generated {fbResult.generated}, failed {fbResult.failed},{" "}
                {fbResult.remaining} remaining.
              </p>
              <ul style={{ paddingLeft: "1.25rem", margin: 0 }}>
                {fbResult.results.map((r) => (
                  <li key={r.submission_id} style={{ color: r.ok ? "#34d399" : "#fb7185" }}>
                    {r.team_name}: {r.ok ? r.verdict : r.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      {overrideTarget && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(8px)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1rem",
          }}
          role="presentation"
          onClick={closeOverride}
        >
          <div
            className="card"
            style={{
              maxWidth: "480px",
              width: "100%",
              margin: 0,
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)",
              border: "1px solid rgba(255, 255, 255, 0.18)",
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="override-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="override-title" style={{ fontSize: "1.25rem", marginBottom: "0.5rem" }}>
              Override score
            </h3>
            <p className="hint" style={{ marginBottom: "1.25rem" }}>
              <strong>{overrideTarget.teamName}</strong> ·{" "}
              <span style={{ textTransform: "capitalize" }}>{overrideTarget.criterion.replace(/_/g, " ")}</span> · AI scored{" "}
              <strong style={{ color: "#a5b4fc" }}>{overrideTarget.current}</strong>
            </p>

            <form onSubmit={handleOverrideSubmit}>
              <div className="form-group">
                <label htmlFor="override-score">New score (1–10)</label>
                <input
                  id="override-score"
                  type="number"
                  min={1}
                  max={10}
                  step={1}
                  value={overrideScoreInput}
                  onChange={(e) => setOverrideScoreInput(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="override-reason">
                  Reason (min {MIN_OVERRIDE_REASON} characters)
                </label>
                <textarea
                  id="override-reason"
                  rows={3}
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Why is the AI's score being adjusted?"
                  required
                />
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: overrideReasonValid ? "#34d399" : "#94a3b8",
                    textAlign: "right",
                  }}
                >
                  {overrideReason.trim().length} / {MIN_OVERRIDE_REASON} min characters
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="override-evaluator">Your name or email</label>
                <input
                  id="override-evaluator"
                  type="text"
                  value={overrideEvaluator}
                  onChange={(e) => setOverrideEvaluator(e.target.value)}
                  placeholder="alice@example.com"
                  required
                />
              </div>

              {overrideError && (
                <div className="alert alert--error" role="alert" style={{ marginBottom: "1rem" }}>
                  <span>{overrideError}</span>
                </div>
              )}

              <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end", marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={closeOverride}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={
                    savingOverride ||
                    !overrideScoreValid ||
                    !overrideReasonValid ||
                    !overrideEvaluatorValid
                  }
                >
                  {savingOverride ? "Saving…" : "Save override"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
