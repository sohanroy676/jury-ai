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

const HEATMAP_COLORS = ["#f3f4f6", "#fef3c7", "#fbbf24", "#f59e0b", "#d97706"];

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
      <h1>Analytics dashboard</h1>
      <p className="subtitle">
        Score distributions, criterion heatmap, and submission funnel for the
        selected track.
      </p>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      <div className="inline-controls">
        <label htmlFor="track-selector">Track</label>
        <TrackSelector activeTrack={activeTrack} onChange={setActiveTrack} />
      </div>
      {loading && <p className="hint">Loading analytics…</p>}
      {!loading && overview && (
        <>
          <section className="stat-row">
            <div className="stat-card">
              <span className="stat-value">{overview.total_submissions}</span>
              <span className="stat-label">Submissions</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">{overview.scored_count}</span>
              <span className="stat-label">Scored</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">{overview.shortlisted_count}</span>
              <span className="stat-label">Shortlisted</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">
                {overview.avg_composite.toFixed(1)}
              </span>
              <span className="stat-label">Avg composite</span>
            </div>
          </section>
          <section className="card">
            <h2>Criterion averages</h2>
            <div className="stat-row">
              {Object.entries(overview.criterion_averages).map(
                ([criterion, avg]) => (
                  <div className="stat-card" key={criterion}>
                    <span className="stat-value">{Number(avg).toFixed(1)}</span>
                    <span className="stat-label">
                      {CRITERIA_LABELS[criterion] ?? criterion}
                    </span>
                  </div>
                )
              )}
            </div>
          </section>
          <section className="card">
            <h2>Score distributions</h2>
            <div className="chart-grid">
              {Object.entries(distributions).map(([criterion, bins]) => (
                <div key={criterion} className="chart-card">
                  <h3>{CRITERIA_LABELS[criterion] ?? criterion}</h3>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={bins}>
                      <XAxis dataKey="score" />
                      <YAxis />
                      <Tooltip />
                      <Bar
                        dataKey="count"
                        fill="#3b82f6"
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          </section>
          {funnel && (
            <section className="card">
              <h2>Submission funnel</h2>
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
                        backgroundColor: `rgba(59, 130, 246, ${pct / 100})`,
                      }}
                    >
                      <span className="funnel-label">{stage.label}</span>
                      <span className="funnel-value">{stage.value}</span>
                      <span className="funnel-pct">{pct}%</span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
          {heatmap.length > 0 && (
            <section className="card">
              <h2>Criterion heatmap (top 20 teams)</h2>
              <div className="heatmap">
                <div className="heatmap-header">
                  <span className="heatmap-team">Team</span>
                  {Object.keys(CRITERIA_LABELS).map((key) => (
                    <span key={key} className="heatmap-criterion">
                      {CRITERIA_LABELS[key]}
                    </span>
                  ))}
                  <span className="heatmap-composite">Avg</span>
                </div>
                {heatmap.map((row) => (
                  <div className="heatmap-row" key={row.submission_id}>
                    <span className="heatmap-team">{row.team_name}</span>
                    {Object.keys(CRITERIA_LABELS).map((criterion) => {
                      const score = row.scores[criterion] ?? 0;
                      return (
                        <span
                          key={criterion}
                          className="heatmap-cell"
                          style={{ backgroundColor: getHeatmapColor(score) }}
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
              <h2>Criterion heatmap</h2>
              <p className="hint">No scored submissions for this track yet.</p>
            </section>
          )}
        </>
      )}
      {!loading && !overview && (
        <section className="card">
          <h2>Analytics</h2>
          <p className="hint">Select a track to view analytics.</p>
        </section>
      )}
    </main>
  );
}
