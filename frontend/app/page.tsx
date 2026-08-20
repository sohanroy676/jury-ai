"use client";

import { useState } from "react";

const ALLOWED_EXTENSIONS = [".pdf", ".pptx"];
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [teamName, setTeamName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setError(null);
    setSuccess(null);

    if (!selected) {
      setFile(null);
      return;
    }

    const ext = selected.name.toLowerCase().split(".").pop();
    if (!ext || !ALLOWED_EXTENSIONS.includes(`.${ext}`)) {
      setError(
        `Unsupported file type ".${ext}". Only .pdf and .pptx are allowed.`
      );
      setFile(null);
      return;
    }

    setFile(selected);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!teamName.trim()) {
      setError("Team name is required.");
      return;
    }
    if (!file) {
      setError("Please select a PDF or PPTX file.");
      return;
    }

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("team_name", teamName);
      formData.append("file", file);

      const resp = await fetch(`${API_URL}/api/submissions`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setError(body.detail ?? `Upload failed (HTTP ${resp.status}).`);
        return;
      }

      const data = await resp.json();
      setSuccess(
        `Submission received! ID: ${data.id}. Status: ${data.status}.`
      );
      setTeamName("");
      setFile(null);
    } catch {
      setError("Network error — could not reach the backend.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main>
      <h1>JuryAI Submission Portal</h1>
      <p className="subtitle">
        Upload your hackathon submission. Only PDF and PPTX files are accepted.
      </p>

      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="team_name">Team name</label>
          <input
            id="team_name"
            type="text"
            value={teamName}
            onChange={(e) => setTeamName(e.target.value)}
            placeholder="e.g. Team Alpha"
            required
          />
        </div>

        <div>
          <label htmlFor="file">Submission file (.pdf / .pptx)</label>
          <input
            id="file"
            type="file"
            accept=".pdf,.pptx"
            onChange={handleFileChange}
            required
          />
        </div>

        {error && <p className="error">{error}</p>}
        {success && <p className="success">{success}</p>}

        <button type="submit" disabled={submitting}>
          {submitting ? "Uploading…" : "Submit"}
        </button>
      </form>
    </main>
  );
}
