"use client";

import { useEffect, useState } from "react";

import { ApiError, TrackInfo, listTracks } from "../lib/api";
import ErrorBanner from "./ErrorBanner";

interface TrackSelectorProps {
  activeTrack: string;
  onChange: (trackId: string) => void;
}

export default function TrackSelector({
  activeTrack,
  onChange,
}: TrackSelectorProps) {
  const [tracks, setTracks] = useState<TrackInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const data = await listTracks();
        const loaded = data.tracks || [];
        const hasDefault = loaded.some((t) => t.id === "default");
        const list = hasDefault
          ? loaded
          : [
              { id: "default", name: "Default Track", description: "Default track" },
              ...loaded,
            ];
        setTracks(list);
      } catch (err) {
        const msg =
          err instanceof ApiError ? err.message : "Could not load tracks.";
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <select disabled>
        <option>Loading tracks…</option>
      </select>
    );
  }

  return (
    <>
      {error && (
        <span className="hint" style={{ color: "#f87171", fontSize: "0.8rem" }}>
          {error}
        </span>
      )}
      <select
        value={activeTrack}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Select evaluation track"
      >
        {tracks.map((track) => (
          <option key={track.id} value={track.id}>
            {track.name}
          </option>
        ))}
      </select>
    </>
  );
}
