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
  const [activeTrack, setActiveTrack] = useState("default");
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
  }, [activeTrack]);

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
      <h1>Track management</h1>
      <p className="subtitle">
        Create and configure evaluation tracks. Each track has its own rubric
        and leaderboard.
      </p>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && <p className="success">{notice}</p>}

      <section className="card">
        <h2>Create new track</h2>
        <form onSubmit={handleCreate}>
          <div className="two-col">
            <div>
              <label htmlFor="new-id">Track ID (slug)</label>
              <input
                id="new-id"
                type="text"
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="e.g. sih-2026"
                disabled={creating}
              />
            </div>
            <div>
              <label htmlFor="new-name">Display name</label>
              <input
                id="new-name"
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Smart India Hackathon 2026"
                disabled={creating}
              />
            </div>
          </div>
          <div>
            <label htmlFor="new-desc">Description (optional)</label>
            <textarea
              id="new-desc"
              rows={2}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="What is this track for?"
              disabled={creating}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={creating}>
            {creating ? "Creating…" : "Create track"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Existing tracks</h2>
        {loading && <p className="hint">Loading tracks…</p>}
        {!loading && (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tracks.map((t) => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td>{t.name}</td>
                  <td>{new Date(t.created_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      size="sm"
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
        )}
      </section>

      <section className="card">
        <h2>Configure track rubric</h2>
        <div className="inline-controls">
          <label htmlFor="track-selector">Track</label>
          <TrackSelector activeTrack={activeTrack} onChange={setActiveTrack} />
        </div>
        <RubricBuilder trackId={activeTrack} />
      </section>
    </main>
  );
}
