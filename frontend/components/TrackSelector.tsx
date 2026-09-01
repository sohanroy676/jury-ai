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
        setTracks(data.tracks);
        // If the active track doesn't exist in the list yet, keep the current
        // selection (e.g. "default" before the seed track loads).
        if (
          data.tracks.length > 0 &&
          !data.tracks.some((t) => t.id === activeTrack)
        ) {
          onChange(data.tracks[0].id);
        }
      } catch (err) {
        const msg =
          err instanceof ApiError ? err.message : "Could not load tracks.";
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, [activeTrack, onChange]);

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
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
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
