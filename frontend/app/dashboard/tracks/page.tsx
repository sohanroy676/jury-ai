"use client";

import { useCallback, useEffect, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import NavLinks from "@/components/NavLinks";
import RubricBuilder from "@/components/RubricBuilder";
import TrackSelector from "@/components/TrackSelector";
import {
  ApiError,
  createTrack,
  deleteTrack,
  listTracks,
  type TrackInfo,
} from "@/lib/api";

export default function TracksPage() {
  const [tracks, setTracks] = useState<TrackInfo[]>([]);
  const [activeTrack, setActiveTrackState] = useState(() => {
    if (typeof window !== "undefined") {
      return sessionStorage.getItem("juryai_active_track") || "default";
    }
    return "default";
  });

  const setActiveTrack = useCallback((trackId: string) => {
    setActiveTrackState(trackId);
    if (typeof window !== "undefined") {
      sessionStorage.setItem("juryai_active_track", trackId);
    }
  }, []);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTracks();
      setTracks(data.tracks);
      if (
        data.tracks.length > 0 &&
        !data.tracks.some((t) => t.id === activeTrack)
      ) {
        setActiveTrack(data.tracks[0].id);
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load tracks."
      );
    } finally {
      setLoading(false);
    }
  }, [activeTrack, setActiveTrack]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newId.trim() || !newName.trim()) {
      setError("Track ID and name are required.");
      return;
    }
    setCreating(true);
    setError(null);
    setNotice(null);
    try {
      await createTrack(
        newId.trim(),
        newName.trim(),
        newDesc.trim() || undefined
      );
      setNewId("");
      setNewName("");
      setNewDesc("");
      setNotice(`Track '${newId}' created.`);
      await load();
      setActiveTrack(newId.trim());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not create track."
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(trackId: string) {
    if (!confirm(`Delete track '${trackId}'? This cannot be undone.`)) return;
    try {
      await deleteTrack(trackId);
      setNotice(`Track '${trackId}' deleted.`);
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not delete track."
      );
    }
  }

  return (
    <main className="wide">
      <NavLinks />

      <section className="card" style={{ padding: "1.75rem 2rem", marginBottom: "1.5rem" }}>
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
          <span>🎯 Track Scoping & Rubric Administration</span>
        </div>
        <h1>Track Management</h1>
        <p className="subtitle" style={{ margin: 0 }}>
          Create and configure isolated evaluation tracks. Each track maintains its own rubric weights, submission pool, and leaderboard.
        </p>
      </section>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="alert alert--success" style={{ marginBottom: "1.5rem" }}>
          <span>{notice}</span>
        </div>
      )}

      <section className="card">
        <h2 className="card__title" style={{ marginBottom: "1.25rem" }}>Create New Evaluation Track</h2>
        <form onSubmit={handleCreate}>
          <div className="two-col">
            <div className="form-group">
              <label htmlFor="new-id">Track Slug / ID</label>
              <input
                id="new-id"
                type="text"
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="e.g. sih-2026-hardware"
                disabled={creating}
              />
            </div>
            <div className="form-group">
              <label htmlFor="new-name">Track Display Name</label>
              <input
                id="new-name"
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Smart India Hackathon - Hardware Track"
                disabled={creating}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="new-desc">Description (Optional)</label>
            <textarea
              id="new-desc"
              rows={2}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="What domain or criteria apply to this track?"
              disabled={creating}
            />
          </div>

          <button type="submit" className="btn btn--primary" disabled={creating}>
            {creating ? "Creating Track…" : "Create Track →"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2 className="card__title" style={{ marginBottom: "1.25rem" }}>Existing Tracks</h2>
        {loading && <p className="hint">Loading tracks…</p>}
        {!loading && (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Track ID</th>
                  <th>Display Name</th>
                  <th>Created Date</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tracks.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <code style={{ background: "rgba(255,255,255,0.08)", padding: "2px 8px", borderRadius: "4px" }}>
                        {t.id}
                      </code>
                    </td>
                    <td style={{ fontWeight: 600 }}>{t.name}</td>
                    <td style={{ color: "#94a3b8" }}>{new Date(t.created_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--danger btn--sm"
                        onClick={() => handleDelete(t.id)}
                        disabled={t.id === "default"}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card__title" style={{ marginBottom: "1rem" }}>Configure Track Rubric</h2>
        <div className="inline-controls">
          <label htmlFor="track-selector">Select Active Track:</label>
          <TrackSelector activeTrack={activeTrack} onChange={setActiveTrack} />
        </div>
        <RubricBuilder trackId={activeTrack} />
      </section>
    </main>
  );
}
