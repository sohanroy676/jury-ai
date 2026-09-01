import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./page";

vi.mock("../../lib/api", () => {
  class FakeApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    API_URL: "http://test",
    ApiError: FakeApiError,
    CRITERIA: ["problem_fit", "technical_depth", "feasibility", "innovation"],
    exportCsvUrl: vi.fn((hackathonId: string, options?: { topN?: number }) =>
      options?.topN != null
        ? `http://test/export.csv?hackathon_id=${hackathonId}&top_n=${options.topN}`
        : `http://test/export.csv?hackathon_id=${hackathonId}`
    ),
    fetchRankings: vi.fn(),
    overrideScore: vi.fn(),
    saveRubric: vi.fn(),
    scorePending: vi.fn(),
    generatePendingFeedback: vi.fn(),
  };
});

vi.mock("../../components/NavLinks", () => ({ default: () => null }));

import * as api from "../../lib/api";

const mockOverrideScore = api.overrideScore as ReturnType<typeof vi.fn>;
const mockRankings = api.fetchRankings as ReturnType<typeof vi.fn>;
const mockSaveRubric = api.saveRubric as ReturnType<typeof vi.fn>;
const mockScorePending = api.scorePending as ReturnType<typeof vi.fn>;
const mockGeneratePending = api.generatePendingFeedback as ReturnType<
  typeof vi.fn
>;

const BOARD = {
  hackathon_id: "default",
  rubric: {
    problem_fit: 0.25,
    technical_depth: 0.25,
    feasibility: 0.25,
    innovation: 0.25,
  },
  rubric_source: "configured",
  shortlist: { top_n: 1, min_score: null },
  ranked: [
    {
      rank: 1,
      submission_id: "id-1",
      team_name: "Moonshot",
      composite_score: 8.5,
      criterion_scores: {
        problem_fit: 9,
        technical_depth: 8,
        feasibility: 8,
        innovation: 9,
      },
      shortlisted: true,
      tied_on_composite: false,
    },
    {
      rank: 2,
      submission_id: "id-2",
      team_name: "Practical",
      composite_score: 7.25,
      criterion_scores: {
        problem_fit: 8,
        technical_depth: 7,
        feasibility: 7,
        innovation: 7,
      },
      shortlisted: false,
      tied_on_composite: true,
    },
  ],
  scored_count: 2,
  unscored_count: 1,
  partial_count: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockRankings.mockResolvedValue(BOARD);
});

async function renderDashboard() {
  render(<DashboardPage />);
  await waitFor(() =>
    expect(mockRankings).toHaveBeenCalledWith("default", { topN: undefined })
  );
}

describe("DashboardPage", () => {
  it("renders ranked teams, composite scores, and shortlist badges", async () => {
    await renderDashboard();

    expect(screen.getByText("Moonshot")).toBeTruthy();
    expect(screen.getByText("Practical")).toBeTruthy();
    expect(screen.getByText("8.50")).toBeTruthy();
    expect(screen.getByText("shortlisted")).toBeTruthy();
    expect(screen.getByText("tie")).toBeTruthy();
    // Counts line reflects the engine's scored/unscored/partial split.
    expect(
      screen.getByText((content) => content.includes("2 scored"))
    ).toBeTruthy();
    expect(
      screen.getByText((content) => content.includes("1 unscored"))
    ).toBeTruthy();
  });

  it("explains the fallback rubric when none is configured", async () => {
    mockRankings.mockResolvedValue({ ...BOARD, rubric_source: "fallback" });
    render(<DashboardPage />);

    await screen.findByText("Moonshot");
    expect(
      screen.getByText((content) =>
        content.includes("using fallback equal weights")
      )
    ).toBeTruthy();
  });

  it("carries the applied Top N cutoff into the CSV export link", async () => {
    await renderDashboard();
    // One ranking was already loaded when the board rendered; the anchor
    // reflects the URL the browser would download.
    let link = screen.getByText("Export CSV").closest("a");
    expect(link?.getAttribute("href")).toContain("hackathon_id=default");
    expect(link?.getAttribute("href")).not.toContain("top_n");

    // Apply a top-n cutoff exactly as an evaluator would.
    fireEvent.change(screen.getByLabelText("Shortlist top"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));

    await waitFor(() =>
      expect(mockRankings).toHaveBeenLastCalledWith("default", { topN: 3 })
    );
    link = screen.getByText("Export CSV").closest("a") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toContain("top_n=3");
  });

  it("shows the empty state when nothing is fully scored", async () => {
    mockRankings.mockResolvedValue({
      ...BOARD,
      ranked: [],
      scored_count: 0,
      unscored_count: 3,
    });
    render(<DashboardPage />);

    await screen.findByText(/No fully-scored submissions yet/);
  });

  it("rejects weights that do not sum to 100 or 1 without calling the API", async () => {
    await renderDashboard();

    fireEvent.change(screen.getByLabelText("innovation"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save rubric/i }));

    await screen.findByRole("alert");
    expect(mockSaveRubric).not.toHaveBeenCalled();
  });

  it("saves valid percentage weights and reloads rankings", async () => {
    mockSaveRubric.mockResolvedValue({
      hackathon_id: "default",
      rubric: BOARD.rubric,
    });
    await renderDashboard();

    fireEvent.click(screen.getByRole("button", { name: /save rubric/i }));

    await waitFor(() => expect(mockSaveRubric).toHaveBeenCalledTimes(1));
    // Initial load + post-save reload.
    await waitFor(() => expect(mockRankings).toHaveBeenCalledTimes(2));
    const body = mockSaveRubric.mock.calls[0][1] as Record<string, number>;
    expect(body.problem_fit).toBeCloseTo(25);
    expect(body.innovation).toBeCloseTo(25);
  });

  it("reports batch scoring outcomes, including per-item failures", async () => {
    mockScorePending.mockResolvedValue({
      scored: 1,
      failed: 1,
      remaining: 0,
      results: [
        {
          submission_id: "id-1",
          team_name: "Moonshot",
          ok: true,
          agent_version: "v1.0.0",
        },
        {
          submission_id: "id-2",
          team_name: "Practical",
          ok: false,
          error: "Scoring failed: API error",
        },
      ],
    });
    await renderDashboard();

    fireEvent.click(
      screen.getByRole("button", { name: /start batch scoring/i })
    );

    await screen.findByText((content) =>
      content.includes("Scored 1, failed 1")
    );
    expect(
      screen.getByText((content) =>
        content.includes("Practical: Scoring failed")
      )
    ).toBeTruthy();
    // The board refreshes after a batch run.
    await waitFor(() => expect(mockRankings).toHaveBeenCalledTimes(2));
  });

  it("generates feedback for all pending teams and reports outcomes", async () => {
    mockGeneratePending.mockResolvedValue({
      generated: 2,
      failed: 0,
      remaining: 0,
      results: [
        {
          submission_id: "id-1",
          team_name: "Moonshot",
          ok: true,
          verdict: "shortlist",
        },
        {
          submission_id: "id-2",
          team_name: "Practical",
          ok: true,
          verdict: "reject",
        },
      ],
    });
    await renderDashboard();

    fireEvent.click(
      screen.getByRole("button", { name: /start feedback generation/i })
    );

    // The applied top-N cutoff rides along (tone + email wording rule).
    await waitFor(() =>
      expect(mockGeneratePending).toHaveBeenCalledWith(10, {
        hackathonId: "default",
        topN: undefined,
      })
    );
    await screen.findByText((content) =>
      content.includes("Generated 2, failed 0")
    );
    // The board refreshes after a batch run.
    await waitFor(() => expect(mockRankings).toHaveBeenCalledTimes(2));
  });

  it("reports per-item feedback failures", async () => {
    mockGeneratePending.mockResolvedValue({
      generated: 1,
      failed: 1,
      remaining: 0,
      results: [
        { submission_id: "id-1", team_name: "Moonshot", ok: true },
        {
          submission_id: "id-2",
          team_name: "Practical",
          ok: false,
          error: "Feedback failed: API error",
        },
      ],
    });
    await renderDashboard();

    fireEvent.click(
      screen.getByRole("button", { name: /start feedback generation/i })
    );

    await screen.findByText((content) =>
      content.includes("Generated 1, failed 1")
    );
    expect(
      screen.getByText((content) =>
        content.includes("Practical: Feedback failed")
      )
    ).toBeTruthy();
  });

  it("surfaces fetch errors in the banner", async () => {
    mockRankings.mockRejectedValue(
      new api.ApiError(503, "Supabase credentials are missing.")
    );
    render(<DashboardPage />);

    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain(
      "Supabase credentials are missing."
    );
  });

  // --- v2.1.0: overrides --------------------------------------------------

  it("opens the override modal with the clicked score pre-filled", async () => {
    await renderDashboard();

    // Moonshot's problem_fit score cell (value 9).
    const cells = screen.getAllByTitle(/Override problem fit for Moonshot/);
    fireEvent.click(cells[0]);

    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("Moonshot");
    expect(dialog.textContent).toContain("problem fit");
    expect(dialog.textContent).toContain("AI scored 9");
    expect(
      (screen.getByLabelText("New score (1–10)") as HTMLInputElement).value
    ).toBe("9");
  });

  it("blocks submission until the reason reaches 10 characters", async () => {
    await renderDashboard();

    fireEvent.click(
      screen.getAllByTitle(/Override problem fit for Moonshot/)[0]
    );
    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("New score (1–10)"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "too short" },
    });
    fireEvent.change(screen.getByLabelText("Your name or email"), {
      target: { value: "alice@example.com" },
    });

    const save = screen.getByRole("button", { name: /save override/i });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(mockOverrideScore).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "The demo clearly shows market fit." },
    });
    expect((save as HTMLButtonElement).disabled).toBe(false);
  });

  it("submits a valid override, shows the new rank, and refreshes", async () => {
    mockOverrideScore.mockResolvedValue({
      submission_id: "id-1",
      criterion: "problem_fit",
      updated_score: { score: 3 },
      rank_context: { rank: 2, composite_score: 6.5 },
    });
    await renderDashboard();

    fireEvent.click(
      screen.getAllByTitle(/Override problem fit for Moonshot/)[0]
    );
    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("New score (1–10)"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "The demo clearly shows market fit." },
    });
    fireEvent.change(screen.getByLabelText("Your name or email"), {
      target: { value: "alice@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save override/i }));

    await waitFor(() =>
      expect(mockOverrideScore).toHaveBeenCalledWith("id-1", "problem_fit", {
        score: 3,
        reason: "The demo clearly shows market fit.",
        evaluator: "alice@example.com",
      })
    );
    // Toast announces the rank consequence of the change.
    await screen.findByText((content) =>
      content.includes("now rank 2 (composite 6.50)")
    );
    // The board reloads after the override.
    await waitFor(() => expect(mockRankings).toHaveBeenCalledTimes(2));
    // The modal is gone.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("surfaces override API errors inside the modal", async () => {
    mockOverrideScore.mockRejectedValue(
      new api.ApiError(
        409,
        "Submission has no 'problem_fit' score to override."
      )
    );
    await renderDashboard();

    fireEvent.click(
      screen.getAllByTitle(/Override problem fit for Moonshot/)[0]
    );
    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("New score (1–10)"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "The demo clearly shows market fit." },
    });
    fireEvent.change(screen.getByLabelText("Your name or email"), {
      target: { value: "alice@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save override/i }));

    const alerts = await screen.findAllByRole("alert");
    expect(
      alerts.some((a) => a.textContent?.includes("no 'problem_fit' score"))
    ).toBe(true);
    // Modal stays open so the evaluator can retry.
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("closes the override modal on cancel without calling the API", async () => {
    await renderDashboard();

    fireEvent.click(
      screen.getAllByTitle(/Override problem fit for Moonshot/)[0]
    );
    await screen.findByRole("dialog");

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mockOverrideScore).not.toHaveBeenCalled();
  });

  // --- v2.1.0: pagination -------------------------------------------------

  function buildBoard(n: number) {
    return {
      ...BOARD,
      ranked: Array.from({ length: n }, (_, i) => ({
        rank: i + 1,
        submission_id: `id-${i + 1}`,
        team_name: `Team ${i + 1}`,
        composite_score: 5 + i / 10,
        criterion_scores: {
          problem_fit: 5,
          technical_depth: 5,
          feasibility: 5,
          innovation: 5,
        },
        shortlisted: false,
        tied_on_composite: false,
      })),
      scored_count: n,
      unscored_count: 0,
      partial_count: 0,
    };
  }

  it("paginates the leaderboard and navigates pages", async () => {
    mockRankings.mockResolvedValue(buildBoard(60));
    await renderDashboard();

    // Default page size 25 shows only the first 25 teams.
    expect(screen.getByText("Team 1")).toBeTruthy();
    expect(screen.queryByText("Team 26")).toBeNull();
    expect(screen.getByText("Page 1 of 3")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /next ›/i }));
    expect(screen.getByText("Team 26")).toBeTruthy();
    expect(screen.queryByText("Team 1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /first page/i }));
    expect(screen.getByText("Team 1")).toBeTruthy();
  });

  it("shows every team on one page for short boards with no pager", async () => {
    mockRankings.mockResolvedValue(buildBoard(2));
    await renderDashboard();

    // Two teams fit on page 1 of 25 — no pagination indicator needed.
    expect(screen.getByText("Team 1")).toBeTruthy();
    expect(screen.getByText("Team 2")).toBeTruthy();
    expect(screen.queryByText("Page 1 of 1")).toBeNull();
  });
});
