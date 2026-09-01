"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import ErrorBanner from "../../components/ErrorBanner";
import NavLinks from "../../components/NavLinks";
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

const HACKATHON_ID = "default";
const MIN_OVERRIDE_REASON = 10;
const PAGE_SIZES = [25, 50, 100] as const;

type WeightInputs = Record<Criterion, string>;

// Percent inputs, seeded to the engine's equal-weights fallback (25 each).
const INITIAL_WEIGHT_INPUTS: WeightInputs = {
  problem_fit: "25",
  technical_depth: "25",
  feasibility: "25",
  innovation: "25",
};

/** One clickable leaderboard score cell awaiting an override. */
interface OverrideTarget {
  submissionId: string;
  teamName: string;
  criterion: Criterion;
  current: number;
}

export default function DashboardPage() {
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

  // --- v2.1.0: pagination + override state ------------------------------
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

  // Success notices self-dismiss so the board never needs a click.
  useEffect(() => {
    if (!notice) return;
    const id = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(id);
  }, [notice]);

  const load = useCallback(async () => {
    setLoadingBoard(true);
    setBoardError(null);
    try {
      const data = await fetchRankings(HACKATHON_ID, { topN: appliedTopN });
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
  }, [appliedTopN]);

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
      await saveRubric(HACKATHON_ID, parsed);
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
      // The applied top-N cutoff drives each team's shortlist flag (and
      // thus its feedback tone + email wording) — same rule as the
      // detail-view Generate button and the export links.
      const result = await generatePendingFeedback(limit, {
        hackathonId: HACKATHON_ID,
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

  // --- v2.1.0: overrides --------------------------------------------------

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

  // --- v2.1.0: client-side pagination -------------------------------------

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
    // Keep the first visible team roughly in view across size changes.
    setPage(Math.floor((safePage * pageSize) / next));
  }

  return (
    <main className="wide">
      <NavLinks />
      <header className="page-header">
        <div>
          <h1>Evaluator dashboard</h1>
          <p className="subtitle">
            Ranked leaderboard, rubric weights, and batch scoring for hackathon{" "}
            <code>{HACKATHON_ID}</code>.
          </p>
        </div>
        <Link className="btn btn-ghost" href="/">
          ← Upload portal
        </Link>
      </header>

      <ErrorBanner message={boardError} onDismiss={() => setBoardError(null)} />

      {notice && (
        <div className="toast toast-success" role="status">
          <span>{notice}</span>
          <button
            type="button"
            className="toast-dismiss"
            aria-label="Dismiss notification"
            onClick={() => setNotice(null)}
          >
            ×
          </button>
        </div>
      )}

      {board && (
        <div className="stat-row" aria-label="Pipeline summary">
          <div className="stat-card">
            <span className="stat-value">{board.scored_count}</span>
            <span className="stat-label">scored</span>
          </div>
          <div className="stat-card stat-card--muted">
            <span className="stat-value">{board.unscored_count}</span>
            <span className="stat-label">unscored</span>
          </div>
          <div className="stat-card stat-card--warn">
            <span className="stat-value">{board.partial_count}</span>
            <span className="stat-label">partial</span>
          </div>
          <p className="counts">
            {board.scored_count} scored · {board.unscored_count} unscored ·{" "}
            {board.partial_count} partial
            {board.rubric_source === "fallback" &&
              " · using fallback equal weights (no rubric configured)"}
          </p>
        </div>
      )}

      <section className="card">
        <h2>Rubric weights (%)</h2>
        <form onSubmit={handleSaveRubric} className="rubric-form">
          {CRITERIA.map((c) => (
            <div key={c}>
              <label htmlFor={`weight-${c}`}>{c.replace(/_/g, " ")}</label>
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
          <button
            className="btn btn-primary"
            type="submit"
            disabled={savingRubric}
          >
            {savingRubric ? "Saving…" : "Save rubric"}
          </button>
        </form>
        <p className="hint">Rankings update immediately after saving.</p>
      </section>

      <section className="card">
        <div className="card-header-row">
          <h2>Leaderboard</h2>
          <form onSubmit={handleApplyTopN} className="inline-controls">
            <label htmlFor="top-n">Shortlist top</label>
            <input
              id="top-n"
              type="number"
              min={1}
              value={topNInput}
              onChange={(e) => setTopNInput(e.target.value)}
            />
            <button className="btn btn-secondary" type="submit">
              Apply
            </button>
            <a
              className="btn btn-ghost"
              href={
                appliedTopN !== undefined
                  ? exportCsvUrl(HACKATHON_ID, { topN: appliedTopN })
                  : exportCsvUrl(HACKATHON_ID)
              }
            >
              Export CSV
            </a>
          </form>
        </div>

        {loadingBoard ? (
          <div className="loading-block" role="status">
            <span className="spinner" aria-hidden="true" />
            Loading rankings…
          </div>
        ) : board && board.ranked.length > 0 ? (
          <>
            <div className="table-scroll">
              <table className="leaderboard">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Team</th>
                    {CRITERIA.map((c) => (
                      <th key={c}>{c.replace(/_/g, " ")}</th>
                    ))}
                    <th>Composite</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.map((row) => (
                    <tr key={row.submission_id}>
                      <td>
                        <span
                          className={`rank-badge${
                            row.rank <= 3 ? ` rank-${row.rank}` : ""
                          }`}
                        >
                          {row.rank}
                        </span>
                      </td>
                      <td>
                        <a
                          className="team-link"
                          href={`/submissions/${row.submission_id}`}
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
                                className="score-cell"
                                title={`Override ${c.replace(/_/g, " ")} for ${row.team_name}`}
                                onClick={() => openOverride(row, c)}
                              >
                                <span className="score-num">{value}</span>
                                <span className="score-bar">
                                  <span
                                    className="score-fill"
                                    style={{ width: `${value * 10}%` }}
                                  />
                                </span>
                              </button>
                            ) : (
                              <span
                                className="score-missing"
                                aria-label="not scored"
                              >
                                —
                              </span>
                            )}
                          </td>
                        );
                      })}
                      <td>
                        <span className="composite">
                          <span className="composite-value">
                            {row.composite_score.toFixed(2)}
                          </span>
                          <span className="score-bar score-bar--composite">
                            <span
                              className="score-fill"
                              style={{ width: `${row.composite_score * 10}%` }}
                            />
                          </span>
                        </span>
                      </td>
                      <td>
                        {row.shortlisted && (
                          <span className="badge badge-shortlist">
                            shortlisted
                          </span>
                        )}
                        {row.tied_on_composite && (
                          <span
                            className="badge badge-tie"
                            title="Tied composite score"
                          >
                            tie
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="table-hint">
              Click any score to override it — a reason is required and the
              original AI score is preserved.
            </p>

            {totalRows > pageSize && (
              <nav className="pagination" aria-label="Leaderboard pages">
                <button
                  type="button"
                  className="btn btn-ghost"
                  aria-label="First page"
                  disabled={safePage === 0}
                  onClick={() => setPage(0)}
                >
                  «
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={safePage === 0}
                  onClick={() => setPage(safePage - 1)}
                >
                  ‹ Prev
                </button>
                <span className="page-indicator">
                  Page {safePage + 1} of {pageCount}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={safePage >= pageCount - 1}
                  onClick={() => setPage(safePage + 1)}
                >
                  Next ›
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  aria-label="Last page"
                  disabled={safePage >= pageCount - 1}
                  onClick={() => setPage(pageCount - 1)}
                >
                  »
                </button>
                <label className="page-size">
                  Rows
                  <select value={pageSize} onChange={handlePageSizeChange}>
                    {PAGE_SIZES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </label>
              </nav>
            )}
          </>
        ) : (
          <div className="empty-state">
            <div className="empty-icon" aria-hidden="true">
              🏆
            </div>
            <h3>No fully-scored submissions yet</h3>
            <p>Run batch scoring below to build the leaderboard.</p>
          </div>
        )}
      </section>

      <div className="two-col">
        <section className="card">
          <h2>Batch scoring</h2>
          <p className="hint">
            Score unscored submissions with the four specialist agents.
          </p>
          <form onSubmit={handleBatchScore} className="inline-controls">
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
              className="btn btn-primary"
              type="submit"
              disabled={batching}
            >
              {batching ? "Scoring…" : "Start batch scoring"}
            </button>
          </form>
          {batchResult && (
            <div className="result-box">
              <p>
                Scored {batchResult.scored}, failed {batchResult.failed},{" "}
                {batchResult.remaining} remaining.
              </p>
              <ul>
                {batchResult.results.map((r) => (
                  <li key={r.submission_id} className={r.ok ? "ok" : "fail"}>
                    {r.team_name}: {r.ok ? "scored" : r.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="card">
          <h2>Batch feedback</h2>
          <p className="hint">
            Generate written feedback for teams that don&apos;t have it yet.
          </p>
          <form onSubmit={handleBatchFeedback} className="inline-controls">
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
              className="btn btn-primary"
              type="submit"
              disabled={generating}
            >
              {generating ? "Generating…" : "Start feedback generation"}
            </button>
          </form>
          {fbResult && (
            <div className="result-box">
              <p>
                Generated {fbResult.generated}, failed {fbResult.failed},{" "}
                {fbResult.remaining} remaining.
              </p>
              <ul>
                {fbResult.results.map((r) => (
                  <li key={r.submission_id} className={r.ok ? "ok" : "fail"}>
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
          className="modal-overlay"
          role="presentation"
          onClick={closeOverride}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="override-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="override-title">Override score</h3>
            <p className="modal-subtitle">
              <strong>{overrideTarget.teamName}</strong> ·{" "}
              {overrideTarget.criterion.replace(/_/g, " ")} · AI scored{" "}
              <strong>{overrideTarget.current}</strong>
            </p>
            <form onSubmit={handleOverrideSubmit}>
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
                className={`char-count${
                  overrideReasonValid ? " char-count--ok" : ""
                }`}
              >
                {overrideReason.trim().length} / {MIN_OVERRIDE_REASON} min
                characters
              </span>
              <label htmlFor="override-evaluator">Your name or email</label>
              <input
                id="override-evaluator"
                type="text"
                value={overrideEvaluator}
                onChange={(e) => setOverrideEvaluator(e.target.value)}
                placeholder="alice@example.com"
                required
              />
              {overrideError && (
                <p className="alert alert-error" role="alert">
                  {overrideError}
                </p>
              )}
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={closeOverride}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
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
