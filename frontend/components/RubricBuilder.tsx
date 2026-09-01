"use client";

import { useCallback, useEffect, useState } from "react";

import { CRITERIA, Weights, fetchLeaderboard, saveRubric } from "../lib/api";
import ErrorBanner from "./ErrorBanner";

interface RubricBuilderProps {
  trackId: string;
}

interface RubricData {
  hackathon_id: string;
  rubric: Weights;
  rubric_source: "configured" | "fallback";
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

    // Auto-normalize: if total exceeds 100%, scale all down proportionally
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
      setNotice("Rubric saved.");
      await load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not save rubric.";
      setError(msg);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="hint">Loading rubric…</p>;
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
    <section className="card">
      <h2>Track rubric: {trackId}</h2>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && <p className="success">{notice}</p>}

      <div className="rubric-builder">
        {CRITERIA.map((criterion) => (
          <div key={criterion} className="rubric-row">
            <label htmlFor={criterion}>
              {criterion.replace(/_/g, " ")}:{" "}
              {Math.round(rubric[criterion] * 100)}%
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
            <span className="rubric-value">{rubric[criterion].toFixed(2)}</span>
          </div>
        ))}
      </div>

      <div className="rubric-summary">
        <p>
          Total: <strong>{Math.round(total * 100)}%</strong>
          {Math.abs(total - 1.0) > 0.01 && (
            <span className="badge badge-tie"> must equal 100%</span>
          )}
        </p>
      </div>

      <button
        type="button"
        className="btn btn-primary"
        disabled={saving || Math.abs(total - 1.0) > 0.01}
        onClick={handleSave}
      >
        {saving ? "Saving…" : "Save rubric"}
      </button>
    </section>
  );
}
