"use client";

import { useCallback, useEffect, useState } from "react";

import NavLinks from "../components/NavLinks";
import {
  ApiError,
  fetchSubmission,
  fetchSubmissions,
  SubmissionRow,
  uploadSubmission,
} from "../lib/api";

const ALLOWED_EXTENSIONS = [".pdf", ".pptx"];
const MAX_UPLOAD_MB = 50;
// Same shape rule the backend enforces (services/email.py is_valid_email).
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Home() {
  const [teamName, setTeamName] = useState("");
  const [teamEmail, setTeamEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
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
      // The portal stays usable without the list (e.g. backend down for
      // scoring but up for uploads is unlikely; a silent empty list beats
      // blocking the upload form).
      setSubmissions(null);
    }
  }, []);

  useEffect(() => {
    void loadSubmissions();
  }, [loadSubmissions]);

  // Pre-submit validation (v1.1.0): format, empty, and size problems are
  // caught the moment a file is chosen — never only on the server.
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
      const data = await uploadSubmission(teamName, recipient, file, {
        replaceExisting,
      });

      // v1.1.0: surface what the parser found so teams immediately see
      // whether their document structure came through. Non-fatal on error.
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
        // Section feedback is a nicety — an unreadable response must not
        // make a successful upload look failed.
      }

      // v1.2.0: reflect the confirmation-email outcome so teams know the
      // notification went out (or why it didn't).
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
          />
        </div>

        <div>
          <label htmlFor="team_email">Contact email</label>
          {/* type="text" + inline validation on purpose (v1.1.0 lesson:
              native constraint validation fights both jsdom tests and the
              styled-message UX); submit is gated by formReady anyway. */}
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

        <div>
          <label htmlFor="file">Submission file (.pdf / .pptx)</label>
          {/* No `required` here on purpose: v1.1.0's inline validation owns
              the messaging (native tooltips would fight it), and submit is
              gated by `formReady` anyway. */}
          <input
            id="file"
            type="file"
            accept=".pdf,.pptx"
            onChange={handleFileChange}
          />
          {fileError && <p className="error">{fileError}</p>}
        </div>

        {error && <p className="error">{error}</p>}
        {conflictMessage && (
          <div className="conflict-box" role="alert">
            <p>{conflictMessage}</p>
            <button
              type="button"
              onClick={() => void doSubmit(true)}
              disabled={submitting}
            >
              {submitting ? "Replacing…" : "Replace previous submission"}
            </button>
            <p className="hint">
              Your earlier version stays in history; only the newest one is
              evaluated.
            </p>
          </div>
        )}
        {success && <p className="success">{success}</p>}

        <button type="submit" disabled={submitting || !formReady}>
          {submitting ? "Uploading…" : "Submit"}
        </button>
        {!formReady && !submitting && (
          <p className="hint">
            A team name, a contact email, and a valid PDF/PPTX file are required
            to submit.
          </p>
        )}
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
