"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import ErrorBanner from "@/components/ErrorBanner";
import NavLinks from "@/components/NavLinks";
import TrackSelector from "@/components/TrackSelector";
import type {
  AnalyticsOverview,
  DistributionBin,
  FunnelData,
  HeatmapRow,
} from "@/lib/api";
import {
  fetchAnalyticsOverview,
  fetchFunnel,
  fetchHeatmap,
  fetchScoreDistributions,
} from "@/lib/api";

const CRITERIA_LABELS: Record<string, string> = {
  problem_fit: "Problem Fit",
  technical_depth: "Technical Depth",
  feasibility: "Feasibility",
  innovation: "Innovation",
};

const HEATMAP_COLORS = [
  "#1e293b",
  "#334155",
  "#f59e0b",
  "#10b981",
  "#6366f1",
];

function getHeatmapColor(score: number): string {
  const idx = Math.min(
    Math.max(0, Math.floor(score / 2)),
    HEATMAP_COLORS.length - 1
  );
  return HEATMAP_COLORS[idx];
}

export default function AnalyticsPage() {
  const [activeTrack, setActiveTrack] = useState("default");
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [distributions, setDistributions] = useState<
    Record<string, DistributionBin[]>
  >({});
  const [funnel, setFunnel] = useState<FunnelData | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    if (!activeTrack) return;
    setLoading(true);
    setError(null);
    try {
      const [ov, dist, fun, hm] = await Promise.all([
        fetchAnalyticsOverview(activeTrack),
        fetchScoreDistributions(activeTrack),
        fetchFunnel(activeTrack),
        fetchHeatmap(activeTrack),
      ]);
      setOverview(ov);
      setDistributions(dist.distributions || {});
      setFunnel(fun.funnel);
      setHeatmap(hm.heatmap || []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load analytics."
      );
    } finally {
      setLoading(false);
    }
  }, [activeTrack]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

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
              <span>📊 Real-Time Evaluation Insights</span>
            </div>
            <h1>Analytics Dashboard</h1>
            <p className="subtitle" style={{ margin: 0 }}>
              Score distribution histograms, team criterion heatmap, and submission funnel metrics.
            </p>
          </div>
          <div className="inline-controls" style={{ margin: 0 }}>
            <label htmlFor="track-selector">Active Track:</label>
            <TrackSelector activeTrack={activeTrack} onChange={setActiveTrack} />
          </div>
        </div>
      </section>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {loading && <p className="hint" style={{ textAlign: "center", padding: "2rem" }}>Loading track analytics…</p>}

      {!loading && overview && (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <span className="stat-card__value">{overview.total_submissions}</span>
              <span className="stat-card__label">Total Submissions</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value" style={{ color: "#38bdf8" }}>{overview.scored_count}</span>
              <span className="stat-card__label">Scored Teams</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value" style={{ color: "#34d399" }}>{overview.shortlisted_count}</span>
              <span className="stat-card__label">Shortlisted</span>
            </div>
            <div className="stat-card">
              <span className="stat-card__value" style={{ color: "#c084fc" }}>
                {overview.avg_composite.toFixed(1)}
              </span>
              <span className="stat-card__label">Avg Composite</span>
            </div>
          </div>

          <section className="card">
            <h2 className="card__title" style={{ marginBottom: "1rem" }}>Criterion Means Breakdown</h2>
            <div className="stat-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", margin: 0 }}>
              {Object.entries(overview.criterion_averages).map(
                ([criterion, avg]) => (
                  <div className="stat-card" key={criterion} style={{ padding: "1rem" }}>
                    <span className="stat-card__value" style={{ fontSize: "1.5rem", color: "#f8fafc" }}>
                      {Number(avg).toFixed(1)}
                    </span>
                    <span className="stat-card__label">
                      {CRITERIA_LABELS[criterion] ?? criterion}
                    </span>
                  </div>
                )
              )}
            </div>
          </section>

          <section className="card">
            <h2 className="card__title" style={{ marginBottom: "1.5rem" }}>Score Distribution Histograms</h2>
            <div className="chart-grid">
              {Object.entries(distributions).map(([criterion, bins]) => (
                <div key={criterion} className="chart-card">
                  <h3>{CRITERIA_LABELS[criterion] ?? criterion}</h3>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={bins} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <XAxis dataKey="score" stroke="#64748b" tick={{ fill: "#94a3b8" }} />
                      <YAxis stroke="#64748b" tick={{ fill: "#94a3b8" }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#0f172a",
                          borderColor: "rgba(255,255,255,0.15)",
                          borderRadius: "8px",
                          color: "#f8fafc",
                        }}
                      />
                      <Bar dataKey="count" fill="#6366f1" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          </section>

          {funnel && (
            <section className="card">
              <h2 className="card__title" style={{ marginBottom: "1.25rem" }}>Submission Pipeline Funnel</h2>
              <div className="funnel">
                {[
                  { label: "Submitted", value: funnel.submitted },
                  { label: "Parsed", value: funnel.parsed },
                  { label: "Scored", value: funnel.scored },
                  { label: "Shortlisted", value: funnel.shortlisted },
                  { label: "Appealed", value: funnel.appealed },
                ].map((stage) => {
                  const pct =
                    funnel.submitted > 0
                      ? Math.round((stage.value / funnel.submitted) * 100)
                      : 0;
                  return (
                    <div
                      className="funnel-stage"
                      key={stage.label}
                      style={{
                        backgroundColor: `rgba(99, 102, 241, ${Math.max(0.12, pct / 100)})`,
                      }}
                    >
                      <span className="funnel-label">{stage.label}</span>
                      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                        <span className="funnel-value">{stage.value}</span>
                        <span className="funnel-pct">({pct}%)</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {heatmap.length > 0 && (
            <section className="card">
              <h2 className="card__title" style={{ marginBottom: "1.25rem" }}>Criterion Heatmap Matrix (Top 20 Teams)</h2>
              <div className="heatmap">
                <div className="heatmap-header">
                  <span className="heatmap-team">Team</span>
                  {Object.keys(CRITERIA_LABELS).map((key) => (
                    <span key={key} className="heatmap-criterion">
                      {CRITERIA_LABELS[key]}
                    </span>
                  ))}
                  <span className="heatmap-composite">Composite</span>
                </div>
                {heatmap.map((row) => (
                  <div className="heatmap-row" key={row.submission_id}>
                    <span className="heatmap-team" style={{ fontWeight: 600 }}>{row.team_name}</span>
                    {Object.keys(CRITERIA_LABELS).map((criterion) => {
                      const score = row.scores[criterion] ?? 0;
                      return (
                        <span
                          key={criterion}
                          className="heatmap-cell"
                          style={{
                            backgroundColor: getHeatmapColor(score),
                            color: score >= 5 ? "#ffffff" : "#cbd5e1",
                          }}
                          title={`${score}/10`}
                        >
                          {score}
                        </span>
                      );
                    })}
                    <span className="heatmap-composite">
                      {row.composite.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {heatmap.length === 0 && !loading && (
            <section className="card">
              <h2 className="card__title">Criterion Heatmap</h2>
              <p className="hint">
                No scored submissions for this track yet.
              </p>
            </section>
          )}
        </>
      )}

      {!loading && !overview && (
        <section className="card">
          <h2 className="card__title">Analytics</h2>
          <p className="hint">Select a track to view analytics.</p>
        </section>
      )}
    </main>
  );
}
