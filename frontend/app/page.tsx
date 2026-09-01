"use client";

import { useCallback, useEffect, useState } from "react";

import NavLinks from "../components/NavLinks";
import {
  ApiError,
  fetchSubmission,
  fetchSubmissions,
  listTracks,
  SubmissionRow,
  TrackInfo,
  uploadSubmission,
} from "../lib/api";

const ALLOWED_EXTENSIONS = [".pdf", ".pptx"];
const MAX_UPLOAD_MB = 50;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Home() {
  const [teamName, setTeamName] = useState("");
  const [teamEmail, setTeamEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [selectedTrack, setSelectedTrack] = useState("default");
  const [tracks, setTracks] = useState<TrackInfo[]>([
    { id: "default", name: "Default Track", created_at: "" },
  ]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [submissions, setSubmissions] = useState<SubmissionRow[] | null>(null);

  const loadSubmissions = useCallback(async () => {
    try {
      setSubmissions(await fetchSubmissions());
    } catch {
      setSubmissions(null);
    }
  }, []);

  useEffect(() => {
    void loadSubmissions();
    void (async () => {
      try {
        const data = await listTracks();
        if (data.tracks && data.tracks.length > 0) {
          setTracks(data.tracks);
        }
      } catch {
        // Fall back to default track
      }
    })();
  }, [loadSubmissions]);

  function validateFile(selected: File): string | null {
    const ext = selected.name.toLowerCase().split(".").pop();
    if (!ext || !ALLOWED_EXTENSIONS.includes(`.${ext}`)) {
      return `Unsupported file type ".${ext}". Only .pdf and .pptx are allowed.`;
    }
    if (selected.size === 0) {
      return "That file looks empty. Please choose a valid PDF or PPTX.";
    }
    if (selected.size > MAX_UPLOAD_MB * 1024 * 1024) {
      const mb = selected.size / (1024 * 1024);
      return `File too large (${mb.toFixed(
        1
      )} MB). The maximum size is ${MAX_UPLOAD_MB} MB.`;
    }
    return null;
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setError(null);
    setSuccess(null);
    setConflictMessage(null);

    if (!selected) {
      setFile(null);
      setFileError(null);
      return;
    }

    const problem = validateFile(selected);
    setFileError(problem);
    setFile(problem ? null : selected);
  }

  async function doSubmit(replaceExisting: boolean) {
    setError(null);
    setSuccess(null);
    setConflictMessage(null);

    if (!teamName.trim()) {
      setError("Team name is required.");
      return;
    }
    const recipient = teamEmail.trim();
    if (!EMAIL_PATTERN.test(recipient)) {
      setError(
        "Please enter a valid contact email so we can send your confirmation."
      );
      return;
    }
    if (!file) {
      setError("Please select a PDF or PPTX file.");
      return;
    }

    setSubmitting(true);
    try {
      const uploadOpts: { replaceExisting?: boolean; hackathonId?: string } = {
        replaceExisting,
      };
      if (selectedTrack && selectedTrack !== "default") {
        uploadOpts.hackathonId = selectedTrack;
      }
      const data = await uploadSubmission(
        teamName,
        recipient,
        file,
        uploadOpts
      );

      let sectionNote = "";
      try {
        const detail = await fetchSubmission(data.id);
        const titles = (detail.parsed?.sections ?? [])
          .map((section) =>
            typeof section === "string"
              ? section
              : String((section as { title?: unknown } | null)?.title ?? "")
          )
          .filter((title) => title.length > 0);
        sectionNote =
          titles.length > 0
            ? ` Parsed sections (${titles.length}): ${titles.join(", ")}.`
            : " No titled sections were detected in the document.";
      } catch {
        // Section feedback non-fatal
      }

      let emailNote = "";
      const confirmation = data.notification?.confirmation_email;
      if (confirmation?.status === "sent") {
        emailNote = ` A confirmation email was sent to ${recipient}.`;
      } else if (confirmation) {
        emailNote =
          " We couldn't send a confirmation email, but your submission was received.";
      }

      setSuccess(
        `Submission received! ID: ${data.id}.${sectionNote}${emailNote}`
      );
      setTeamName("");
      setTeamEmail("");
      setFile(null);
      void loadSubmissions();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflictMessage(err.message);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unexpected error during upload.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void doSubmit(false);
  }

  const trimmedEmail = teamEmail.trim();
  const emailValid = EMAIL_PATTERN.test(trimmedEmail);
  const showEmailError = teamEmail.length > 0 && !emailValid;
  const formReady = Boolean(teamName.trim()) && emailValid && file !== null;

  return (
    <main>
      <NavLinks />

      <section className="card" style={{ textAlign: "center", padding: "2.5rem 1.5rem" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.25rem 0.75rem",
            borderRadius: "9999px",
            background: "rgba(99, 102, 241, 0.15)",
            border: "1px solid rgba(99, 102, 241, 0.3)",
            color: "#a5b4fc",
            fontSize: "0.8125rem",
            fontWeight: 600,
            marginBottom: "1rem",
          }}
        >
          <span>⚡ Automated AI Jury System</span>
        </div>
        <h1 style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>
          JuryAI Submission Portal
        </h1>
        <p className="subtitle" style={{ maxWidth: "520px", margin: "0 auto 1.5rem" }}>
          Upload your hackathon submission. Only PDF and PPTX files are accepted (up to 50MB).
          Our 4 specialist AI scoring agents will evaluate your team automatically.
        </p>
      </section>

      <form onSubmit={handleSubmit} className="card">
        <h2 className="card__title" style={{ marginBottom: "1.25rem" }}>
          Submission Form
        </h2>

        <div className="form-group">
          <label htmlFor="team_name">Team name</label>
          <input
            id="team_name"
            type="text"
            value={teamName}
            onChange={(e) => setTeamName(e.target.value)}
            placeholder="e.g. QuantumQuokka"
          />
        </div>

        <div className="form-group">
          <label htmlFor="track">Evaluation track</label>
          <select
            id="track"
            value={selectedTrack}
            onChange={(e) => setSelectedTrack(e.target.value)}
          >
            {tracks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.id})
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="team_email">Contact email</label>
          <input
            id="team_email"
            type="text"
            value={teamEmail}
            onChange={(e) => setTeamEmail(e.target.value)}
            placeholder="results & confirmation will be mailed here"
          />
          {showEmailError && (
            <p className="error">Please enter a valid email address.</p>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="file">Submission file (.pdf / .pptx)</label>
          <div
            style={{
              border: "2px dashed rgba(255, 255, 255, 0.15)",
              borderRadius: "12px",
              padding: "1.25rem",
              background: "rgba(15, 23, 42, 0.4)",
              textAlign: "center",
              transition: "border-color 200ms ease",
            }}
          >
            <input
              id="file"
              type="file"
              accept=".pdf,.pptx"
              onChange={handleFileChange}
              style={{ cursor: "pointer" }}
            />
            {file && (
              <p style={{ marginTop: "0.5rem", color: "#34d399", fontSize: "0.875rem", fontWeight: 500 }}>
                ✓ Selected: {file.name} ({(file.size / (1024 * 1024)).toFixed(2)} MB)
              </p>
            )}
          </div>
          {fileError && <p className="error">{fileError}</p>}
        </div>

        {error && <p className="error">{error}</p>}

        {conflictMessage && (
          <div className="conflict-box" role="alert">
            <p style={{ fontWeight: 600 }}>⚠️ Duplicate Submission Detected</p>
            <p>{conflictMessage}</p>
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => void doSubmit(true)}
              disabled={submitting}
            >
              {submitting ? "Replacing…" : "Replace previous submission"}
            </button>
            <p className="hint">
              Your earlier version stays in history; only the newest version is evaluated.
            </p>
          </div>
        )}

        {success && (
          <div className="alert alert--success" style={{ marginBottom: "1rem" }}>
            <span>{success}</span>
          </div>
        )}

        <button
          type="submit"
          className="btn btn--primary"
          style={{ width: "100%", padding: "0.85rem", marginTop: "0.5rem" }}
          disabled={submitting || !formReady}
        >
          {submitting ? "Uploading…" : "Submit"}
        </button>

        {!formReady && !submitting && (
          <p className="hint" style={{ textAlign: "center", marginTop: "0.75rem" }}>
            A team name, a contact email, and a valid PDF/PPTX file are required to submit.
          </p>
        )}
      </form>

      <section className="card">
        <div className="card__header">
          <h2 className="card__title">Recent Submissions</h2>
          {submissions && (
            <span className="badge badge--ai">
              {submissions.length} Total
            </span>
          )}
        </div>
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
                <div>
                  <a href={`/submissions/${s.id}`}>{s.team_name}</a>
                  <span className="meta" style={{ display: "block", marginTop: "0.2rem" }}>
                    {s.file_type?.toUpperCase() || ""}
                    {s.status ? ` · ${s.status}` : ""}
                    {s.uploaded_at ? ` · ${new Date(s.uploaded_at).toLocaleString()}` : ""}
                  </span>
                </div>
                <a href={`/submissions/${s.id}`} className="btn btn--secondary btn--sm">
                  View →
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
