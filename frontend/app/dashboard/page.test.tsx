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
    saveRubric: vi.fn(),
    scorePending: vi.fn(),
  };
});

vi.mock("../../components/NavLinks", () => ({ default: () => null }));

import * as api from "../../lib/api";

const mockRankings = api.fetchRankings as ReturnType<typeof vi.fn>;
const mockSaveRubric = api.saveRubric as ReturnType<typeof vi.fn>;
const mockScorePending = api.scorePending as ReturnType<typeof vi.fn>;

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
});
