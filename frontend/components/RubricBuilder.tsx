"use client";

import { useCallback, useEffect, useState } from "react";

import { CRITERIA, Weights, fetchLeaderboard, saveRubric } from "../lib/api";
import ErrorBanner from "./ErrorBanner";

interface RubricBuilderProps {
  trackId: string;
}

export default function RubricBuilder({ trackId }: RubricBuilderProps) {
  const [rubric, setRubric] = useState<Weights | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLeaderboard(trackId);
      setRubric(data.rubric);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Could not load the rubric.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [trackId]);

  useEffect(() => {
    void load();
  }, [load]);

  function handleWeightChange(criterion: string, value: number) {
    if (!rubric) return;
    const updated = { ...rubric, [criterion]: value };
    const total = Object.values(updated).reduce((sum, v) => sum + v, 0);

    if (total > 1) {
      const scale = 1 / total;
      Object.keys(updated).forEach((k) => {
        updated[k as keyof Weights] =
          Math.round(updated[k as keyof Weights] * scale * 100) / 100;
      });
    }
    setRubric(updated);
  }

  async function handleSave() {
    if (!rubric) return;
    const total = Object.values(rubric).reduce((sum, v) => sum + v, 0);
    if (Math.abs(total - 1.0) > 0.01) {
      setError("Weights must sum to 1.0 (100%).");
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await saveRubric(trackId, rubric);
      setNotice("Rubric saved successfully.");
      await load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not save rubric.";
      setError(msg);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="hint">Loading rubric for track '{trackId}'…</p>;
  }

  if (!rubric) {
    return (
      <ErrorBanner
        message={error ?? "Rubric not found."}
        onDismiss={() => setError(null)}
      />
    );
  }

  const total = Object.values(rubric).reduce((sum, v) => sum + v, 0);

  return (
    <div style={{ marginTop: "1rem" }}>
      <h3 style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
        Configuring Track Rubric: <strong style={{ color: "#a5b4fc" }}>{trackId}</strong>
      </h3>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="alert alert--success" style={{ marginBottom: "1rem" }}>
          <span>{notice}</span>
        </div>
      )}

      <div className="rubric-builder">
        {CRITERIA.map((criterion) => (
          <div key={criterion} className="rubric-row">
            <label htmlFor={criterion} style={{ textTransform: "capitalize" }}>
              {criterion.replace(/_/g, " ")}
            </label>
            <input
              id={criterion}
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(rubric[criterion] * 100)}
              onChange={(e) =>
                handleWeightChange(criterion, Number(e.target.value) / 100)
              }
            />
            <span className="rubric-value">
              {Math.round(rubric[criterion] * 100)}%
            </span>
          </div>
        ))}
      </div>

      <div className="rubric-summary" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p style={{ margin: 0 }}>
          Total Weight Sum: <strong>{Math.round(total * 100)}%</strong>
          {Math.abs(total - 1.0) > 0.01 && (
            <span className="badge badge--tie" style={{ marginLeft: "0.75rem" }}>
              Must equal 100%
            </span>
          )}
        </p>

        <button
          type="button"
          className="btn btn--primary"
          disabled={saving || Math.abs(total - 1.0) > 0.01}
          onClick={handleSave}
        >
          {saving ? "Saving Rubric…" : "Save Track Rubric"}
        </button>
      </div>
    </div>
  );
}
