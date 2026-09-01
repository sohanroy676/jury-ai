// Typed API client for the JuryAI backend (v1.0.0 evaluator dashboard).
//
// Every page talks to the backend exclusively through this module so
// error handling stays in one place: network failures, rate limits, and
// unconfigured services all map to human-readable messages instead of
// leaking internals.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const CRITERIA = [
  "problem_fit",
  "technical_depth",
  "feasibility",
  "innovation",
] as const;

export type Criterion = (typeof CRITERIA)[number];

export type Weights = Record<Criterion, number>;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function friendlyMessage(status: number, detail: unknown): string {
  // Prefer the backend's own detail when it is a plain string — the API
  // already writes operator-facing messages ("Supabase credentials are
  // missing...", "Provide either top_n or min_score..."). Only known
  // opaque cases get replaced wholesale.
  const backendDetail =
    typeof detail === "string" && detail.trim().length > 0 ? detail : null;

  switch (status) {
    case 429:
      return "Rate limit reached on the free LLM tier. Wait about a minute and try again.";
    default:
      return backendDetail ?? `Request failed (HTTP ${status}).`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Network error — could not reach the backend.");
  }

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}) as { detail?: unknown });
    throw new ApiError(resp.status, friendlyMessage(resp.status, body.detail));
  }

  return (await resp.json()) as T;
}

// --- Types mirroring the backend responses -----------------------------

export interface SubmissionRow {
  id: string;
  team_name: string;
  file_url?: string;
  file_type?: string;
  status?: string | null;
  uploaded_at?: string;
}

export interface RankedRow {
  rank: number;
  submission_id: string;
  team_name: string;
  composite_score: number;
  criterion_scores: Record<string, number>;
  shortlisted: boolean;
  tied_on_composite: boolean;
}

export interface Leaderboard {
  hackathon_id: string;
  rubric: Record<string, number>;
  rubric_source: "configured" | "fallback";
  shortlist: { top_n: number | null; min_score: number | null };
  ranked: RankedRow[];
  scored_count: number;
  unscored_count: number;
  partial_count: number;
}

export interface ScoreRow {
  criterion: string;
  score: number;
  justification: string;
  cited_excerpt?: string;
  // v2.1.0 override provenance (null until a human adjusts the score).
  original_score?: number | null;
  overridden_at?: string | null;
  overridden_by?: string | null;
  override_reason?: string | null;
}

export interface ParsedInfo {
  raw_text?: string;
  sections?: unknown[];
  source_format?: string;
}

// v2.1.0: an image the CLIP router flagged for human confirmation
// (low classification confidence or a failed vision description).
export interface FlaggedImage {
  page?: number;
  slide?: number;
  classification?: string;
  confidence?: number;
  description?: string | null;
  needs_human_review?: boolean;
}

export interface SubmissionDetail {
  submission: SubmissionRow;
  parsed: ParsedInfo | null;
  scores: ScoreRow[] | null;
  flagged_images?: FlaggedImage[];
}

export interface FeedbackRecord {
  strengths: string[];
  weaknesses: string[];
  suggestion: string;
  verdict: "shortlist" | "reject";
  agent_version?: string;
  generated_at?: string;
}

export interface BatchScoreItem {
  submission_id: string;
  team_name: string;
  ok: boolean;
  agent_version?: string;
  error?: string;
}

export interface BatchScoreResult {
  scored: number;
  failed: number;
  remaining: number;
  results: BatchScoreItem[];
}

export interface UploadedSubmission {
  id: string;
  team_name: string;
  status?: string;
  uploaded_at?: string;
  team_email?: string | null;
  /** v1.2.0: notification outcomes ride along on the upload response. */
  notification?: {
    confirmation_email?: { status: string; reason?: string };
  };
}

// --- Endpoints ----------------------------------------------------------

export function fetchSubmissions(): Promise<SubmissionRow[]> {
  return request<SubmissionRow[]>("/api/submissions");
}

export function fetchSubmission(
  submissionId: string
): Promise<SubmissionDetail> {
  return request<SubmissionDetail>(
    `/api/submissions/${encodeURIComponent(submissionId)}`
  );
}

// v1.1.0: the multipart upload lives here (not in the portal page) so
// every backend call funnels through this module's error mapping. A 409
// means the team already has an active submission — the caller shows its
// "replace previous version" confirmation and retries with replaceExisting.
// v1.2.0: teamEmail rides along so the backend can send the confirmation
// now and the results-with-feedback email later.
export async function uploadSubmission(
  teamName: string,
  teamEmail: string,
  file: File,
  options: { replaceExisting?: boolean } = {}
): Promise<UploadedSubmission> {
  const formData = new FormData();
  formData.append("team_name", teamName);
  formData.append("team_email", teamEmail);
  formData.append("file", file);
  if (options.replaceExisting) {
    formData.append("replace_existing", "true");
  }

  let resp: Response;
  try {
    resp = await fetch(`${API_URL}/api/submissions`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new ApiError(0, "Network error — could not reach the backend.");
  }

  const body = await resp.json().catch(() => ({}) as { detail?: unknown });
  if (!resp.ok) {
    throw new ApiError(resp.status, friendlyMessage(resp.status, body.detail));
  }
  return body as UploadedSubmission;
}

export async function fetchRankings(
  hackathonId: string,
  options: { topN?: number; minScore?: number } = {}
): Promise<Leaderboard> {
  const params = new URLSearchParams({ hackathon_id: hackathonId });
  if (options.topN != null) params.set("top_n", String(options.topN));
  if (options.minScore != null)
    params.set("min_score", String(options.minScore));
  return request<Leaderboard>(`/api/rankings?${params.toString()}`);
}

export async function fetchRubric(
  hackathonId: string
): Promise<{ hackathon_id: string; rubric: Weights | null }> {
  return request(`/api/rubrics/${encodeURIComponent(hackathonId)}`);
}

export async function saveRubric(
  hackathonId: string,
  weights: Weights
): Promise<{ hackathon_id: string; rubric: Weights }> {
  return request(`/api/rubrics/${encodeURIComponent(hackathonId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ weights }),
  });
}

export interface ScoreResponse {
  submission_id: string;
  agent_version: string;
  scores: ScoreRow[];
}

export function triggerScore(submissionId: string): Promise<ScoreResponse> {
  return request<ScoreResponse>(
    `/api/submissions/${encodeURIComponent(submissionId)}/score`,
    { method: "POST" }
  );
}

// --- v2.1.0: evaluator score overrides ---------------------------------

export interface OverrideResponse {
  submission_id: string;
  criterion: string;
  updated_score: ScoreRow;
  rank_context: Partial<RankedRow>;
}

export function overrideScore(
  submissionId: string,
  criterion: Criterion,
  body: { score: number; reason: string; evaluator: string }
): Promise<OverrideResponse> {
  return request<OverrideResponse>(
    `/api/submissions/${encodeURIComponent(submissionId)}/scores/${encodeURIComponent(
      criterion
    )}`,
    { method: "PUT", body: JSON.stringify(body) }
  );
}

export function triggerFeedback(
  submissionId: string,
  options: { hackathonId?: string; topN?: number } = {}
): Promise<FeedbackRecord> {
  const params = new URLSearchParams({
    hackathon_id: options.hackathonId ?? "default",
    top_n: String(options.topN ?? 5),
  });
  return request(
    `/api/submissions/${encodeURIComponent(submissionId)}/feedback?${params.toString()}`,
    { method: "POST" }
  );
}

export function fetchFeedback(
  submissionId: string
): Promise<{ submission_id: string; feedback: FeedbackRecord | null }> {
  return request(
    `/api/submissions/${encodeURIComponent(submissionId)}/feedback`
  );
}

export function scorePending(limit: number): Promise<BatchScoreResult> {
  return request<BatchScoreResult>(
    `/api/submissions/score-pending?limit=${encodeURIComponent(String(limit))}`,
    { method: "POST" }
  );
}

export interface BatchFeedbackItem {
  submission_id: string;
  team_name: string;
  ok: boolean;
  verdict?: string;
  error?: string;
}

export interface BatchFeedbackResult {
  generated: number;
  failed: number;
  remaining: number;
  results: BatchFeedbackItem[];
}

// v1.2.0: batch counterpart of triggerFeedback — generates feedback for
// every ranked team lacking a current feedback row (best composite
// first), sending each team its results email as it goes.
export function generatePendingFeedback(
  limit: number,
  options: { hackathonId?: string; topN?: number } = {}
): Promise<BatchFeedbackResult> {
  const params = new URLSearchParams({
    limit: String(limit),
    hackathon_id: options.hackathonId ?? "default",
    top_n: String(options.topN ?? 5),
  });
  return request<BatchFeedbackResult>(
    `/api/submissions/feedback-pending?${params.toString()}`,
    { method: "POST" }
  );
}

// --- Export URLs (direct downloads, no JSON wrapper) --------------------

export function exportCsvUrl(
  hackathonId: string,
  options: { topN?: number; minScore?: number } = {}
): string {
  // Manual query building (not URLSearchParams) so space encoding stays
  // byte-compatible with the original encodeURIComponent contract.
  const parts = [`hackathon_id=${encodeURIComponent(hackathonId)}`];
  if (options.topN != null) parts.push(`top_n=${options.topN}`);
  if (options.minScore != null) parts.push(`min_score=${options.minScore}`);
  return `${API_URL}/api/export/csv?${parts.join("&")}`;
}

// The shortlist cutoff rides along so a downloaded report reflects the
// same context the evaluator was looking at — without it the engine
// treats "no cutoff" as nobody-shortlisted (v1.1 CSV bug).
export function exportPdfUrl(
  submissionId: string,
  options: { hackathonId?: string; topN?: number } = {}
): string {
  const parts = [
    `hackathon_id=${encodeURIComponent(options.hackathonId ?? "default")}`,
  ];
  if (options.topN != null) parts.push(`top_n=${options.topN}`);
  return `${API_URL}/api/export/submissions/${encodeURIComponent(
    submissionId
  )}/pdf?${parts.join("&")}`;
}
