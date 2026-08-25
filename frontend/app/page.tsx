"use client";

import { useCallback, useEffect, useState } from "react";

import NavLinks from "../components/NavLinks";
import { fetchSubmissions, SubmissionRow } from "../lib/api";

const ALLOWED_EXTENSIONS = [".pdf", ".pptx"];
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [teamName, setTeamName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [submissions, setSubmissions] = useState<SubmissionRow[] | null>(null);

  const loadSubmissions = useCallback(async () => {
    try {
      setSubmissions(await fetchSubmissions());
    } catch {
      // The portal stays usable without the list (e.g. backend down for
      // scoring but up for uploads is unlikely; a silent empty list beats
      // blocking the upload form).
      setSubmissions(null);
    }
  }, []);

  useEffect(() => {
    void loadSubmissions();
  }, [loadSubmissions]);

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
      void loadSubmissions();
    } catch {
      setError("Network error — could not reach the backend.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main>
      <NavLinks />
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

      <section className="card">
        <h2>Recent submissions</h2>
        {submissions === null ? (
          <p className="hint">
            Could not load the submissions list (is the backend running?).
          </p>
        ) : submissions.length === 0 ? (
          <p className="hint">No submissions yet — be the first to upload.</p>
        ) : (
          <ul className="submission-list">
            {submissions.map((s) => (
              <li key={s.id}>
                <a href={`/submissions/${s.id}`}>{s.team_name}</a>
                <span className="meta">
                  {" "}
                  {s.file_type?.toUpperCase() || ""}
                  {s.status ? ` · ${s.status}` : ""}
                  {s.uploaded_at ? ` · ${s.uploaded_at}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
