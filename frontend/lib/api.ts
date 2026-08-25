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
}

export interface ParsedInfo {
  raw_text?: string;
  sections?: unknown[];
  source_format?: string;
}

export interface SubmissionDetail {
  submission: SubmissionRow;
  parsed: ParsedInfo | null;
  scores: ScoreRow[] | null;
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

// --- Export URLs (direct downloads, no JSON wrapper) --------------------

export function exportCsvUrl(hackathonId: string): string {
  return `${API_URL}/api/export/csv?hackathon_id=${encodeURIComponent(hackathonId)}`;
}

export function exportPdfUrl(submissionId: string): string {
  return `${API_URL}/api/export/submissions/${encodeURIComponent(submissionId)}/pdf`;
}
