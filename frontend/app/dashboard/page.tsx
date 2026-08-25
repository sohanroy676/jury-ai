"use client";

import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "../../components/ErrorBanner";
import NavLinks from "../../components/NavLinks";
import {
  ApiError,
  BatchScoreResult,
  CRITERIA,
  Criterion,
  Leaderboard,
  exportCsvUrl,
  fetchRankings,
  saveRubric,
  scorePending,
} from "../../lib/api";
import type { Weights } from "../../lib/api";

const HACKATHON_ID = "default";

type WeightInputs = Record<Criterion, string>;

// Percent inputs, seeded to the engine's equal-weights fallback (25 each).
const INITIAL_WEIGHT_INPUTS: WeightInputs = {
  problem_fit: "25",
  technical_depth: "25",
  feasibility: "25",
  innovation: "25",
};

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

  return (
    <main className="wide">
      <NavLinks />
      <h1>Evaluator dashboard</h1>
      <p className="subtitle">
        Ranked leaderboard, rubric weights, and batch scoring for hackathon{" "}
        <code>{HACKATHON_ID}</code>.
      </p>

      <ErrorBanner message={boardError} onDismiss={() => setBoardError(null)} />

      {board && (
        <p className="counts">
          {board.scored_count} scored · {board.unscored_count} unscored ·{" "}
          {board.partial_count} partial
          {board.rubric_source === "fallback" &&
            " · using fallback equal weights (no rubric configured)"}
        </p>
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
          <button type="submit" disabled={savingRubric}>
            {savingRubric ? "Saving…" : "Save rubric"}
          </button>
        </form>
        <p className="hint">Rankings update immediately after saving.</p>
      </section>

      <section className="card">
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
          <button type="submit">Apply</button>
          <a
            className="button-link"
            href={
              appliedTopN !== undefined
                ? exportCsvUrl(HACKATHON_ID, { topN: appliedTopN })
                : exportCsvUrl(HACKATHON_ID)
            }
          >
            Export CSV
          </a>
        </form>

        {loadingBoard ? (
          <p>Loading rankings…</p>
        ) : board && board.ranked.length > 0 ? (
          <table className="leaderboard">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Team</th>
                {CRITERIA.map((c) => (
                  <th key={c}>{c.replace(/_/g, " ")}</th>
                ))}
                <th>Composite</th>
                <th>Shortlisted</th>
              </tr>
            </thead>
            <tbody>
              {board.ranked.map((row) => (
                <tr key={row.submission_id}>
                  <td>{row.rank}</td>
                  <td>
                    <a href={`/submissions/${row.submission_id}`}>
                      {row.team_name}
                    </a>
                  </td>
                  {CRITERIA.map((c) => (
                    <td key={c}>{row.criterion_scores[c] ?? "—"}</td>
                  ))}
                  <td>{row.composite_score.toFixed(2)}</td>
                  <td>
                    {row.shortlisted && (
                      <span className="badge badge-shortlist">shortlisted</span>
                    )}
                    {row.tied_on_composite && (
                      <span
                        className="badge badge-tie"
                        title="Tied composite score"
                      >
                        tie
                      </span>
                    )}
                    {!row.shortlisted && !row.tied_on_composite && "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No fully-scored submissions yet — trigger scoring below.</p>
        )}
      </section>

      <section className="card">
        <h2>Score all pending</h2>
        <p className="hint">
          Sequentially scores every submission that lacks a complete score set.
          One submission at a time keeps the run inside the free LLM rate
          limits.
        </p>
        <div className="inline-controls">
          <label htmlFor="batch-limit">Batch size (max 50)</label>
          <input
            id="batch-limit"
            type="number"
            min={1}
            max={50}
            value={batchLimitInput}
            onChange={(e) => setBatchLimitInput(e.target.value)}
          />
          <button type="button" onClick={handleBatchScore} disabled={batching}>
            {batching ? "Scoring…" : "Start batch scoring"}
          </button>
        </div>
        {batchResult && (
          <div className="batch-result">
            <p className={batchResult.failed > 0 ? "error" : "success"}>
              Scored {batchResult.scored}, failed {batchResult.failed},{" "}
              {batchResult.remaining} remaining.
            </p>
            {batchResult.results
              .filter((r) => !r.ok)
              .map((r) => (
                <p key={r.submission_id} className="error">
                  {r.team_name || r.submission_id}: {r.error}
                </p>
              ))}
          </div>
        )}
      </section>
    </main>
  );
}
