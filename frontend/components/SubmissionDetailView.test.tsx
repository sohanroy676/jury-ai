import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SubmissionDetailView from "./SubmissionDetailView";

vi.mock("../lib/api", () => {
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
    exportPdfUrl: () => "http://test/pdf",
    fetchFeedback: vi.fn(),
    fetchSubmission: vi.fn(),
    triggerFeedback: vi.fn(),
    triggerScore: vi.fn(),
  };
});

vi.mock("./NavLinks", () => ({ default: () => null }));

import * as api from "../lib/api";

const mockFetchSubmission = api.fetchSubmission as ReturnType<typeof vi.fn>;
const mockFetchFeedback = api.fetchFeedback as ReturnType<typeof vi.fn>;
const mockTriggerScore = api.triggerScore as ReturnType<typeof vi.fn>;
const mockTriggerFeedback = api.triggerFeedback as ReturnType<typeof vi.fn>;

const SUBMISSION = {
  submission: {
    id: "sub-1",
    team_name: "Quantum Quokka",
    file_type: "pdf",
    status: "parsed",
    uploaded_at: "2026-08-25",
  },
  parsed: {
    raw_text: "We solve X with Y.",
    source_format: "pdf",
    sections: [],
  },
  scores: [
    {
      criterion: "problem_fit",
      score: 9,
      justification: "Clear problem statement.",
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchSubmission.mockResolvedValue(SUBMISSION);
  mockFetchFeedback.mockResolvedValue({
    submission_id: "sub-1",
    feedback: null,
  });
});

async function renderDetail() {
  render(<SubmissionDetailView submissionId="sub-1" />);
  await waitFor(() =>
    expect(mockFetchSubmission).toHaveBeenCalledWith("sub-1")
  );
}

describe("SubmissionDetailView", () => {
  it("renders the team, metadata, and criterion scores", async () => {
    await renderDetail();

    expect(screen.getByText("Quantum Quokka")).toBeTruthy();
    // The component renders criterion keys with underscores replaced by
    // spaces (lowercase), matching the dashboard's label convention.
    expect(screen.getByText("problem fit")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
    expect(screen.getByText("Clear problem statement.")).toBeTruthy();
  });

  it("triggers scoring and refreshes the detail", async () => {
    mockTriggerScore.mockResolvedValue({
      submission_id: "sub-1",
      agent_version: "v1.0.0",
      scores: SUBMISSION.scores,
    });
    await renderDetail();

    fireEvent.click(
      screen.getByRole("button", { name: /score this submission/i })
    );

    await waitFor(() => expect(mockTriggerScore).toHaveBeenCalledWith("sub-1"));
    // The component reloads after scoring.
    await waitFor(() =>
      expect(mockFetchSubmission.mock.calls.length).toBeGreaterThan(1)
    );
    expect(
      screen.getByText((content) => content.includes("Scored by agent v1.0.0"))
    ).toBeTruthy();
  });

  it("triggers feedback with the topN cutoff and renders the verdict", async () => {
    mockTriggerFeedback.mockResolvedValue({
      strengths: ["Great problem."],
      weaknesses: ["Thin details."],
      suggestion: "Expand the architecture section.",
      verdict: "shortlist",
    });
    await renderDetail();

    fireEvent.change(screen.getByLabelText(/shortlist cutoff top n/i), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: /generate feedback/i }));

    await waitFor(() =>
      expect(mockTriggerFeedback).toHaveBeenCalledWith("sub-1", { topN: 3 })
    );
    expect(screen.getByText("shortlist")).toBeTruthy();
    expect(screen.getByText("Great problem.")).toBeTruthy();
  });

  it("renders a 409-style failure message in the alert banner", async () => {
    mockTriggerFeedback.mockRejectedValue(
      new api.ApiError(
        409,
        "Submission sub-1 has no complete score set. Trigger scoring first."
      )
    );
    await renderDetail();

    fireEvent.click(screen.getByRole("button", { name: /generate feedback/i }));

    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain(
      "has no complete score set"
    );
  });

  it("shows a friendly message when feedback is missing", async () => {
    await renderDetail();
    expect(screen.getByText("No feedback generated yet.")).toBeTruthy();
    expect(screen.getByText("Download PDF report")).toBeTruthy();
  });

  // --- v1.1.0 stage tracker + polling ---------------------------------------

  it("renders the derived pipeline stages in the tracker", async () => {
    await renderDetail();

    const tracker = screen.getByLabelText("Submission progress");
    expect(tracker.textContent).toContain("Submitted");
    expect(tracker.textContent).toContain("Parsed");
    expect(tracker.textContent).toContain("Scored");
    // Only ONE criterion score exists in SUBMISSION -> not scored-complete.
    expect(tracker.textContent).toContain("Awaiting result");
  });

  it("shows the verdict stage once feedback exists", async () => {
    mockFetchFeedback.mockResolvedValue({
      submission_id: "sub-1",
      feedback: {
        strengths: [],
        weaknesses: [],
        suggestion: "ok",
        verdict: "reject",
      },
    });
    await renderDetail();

    const tracker = screen.getByLabelText("Submission progress");
    expect(tracker.textContent).toContain("Rejected");
    expect(tracker.textContent).not.toContain("Awaiting result");
  });

  it("polls every 10s until a verdict arrives, then stops", async () => {
    vi.useFakeTimers();
    try {
      const { act } = await import("@testing-library/react");
      render(<SubmissionDetailView submissionId="sub-1" />);

      // Flush the initial load (two awaited fetches).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(mockFetchSubmission).toHaveBeenCalledTimes(1);

      // One polling interval fires a second load.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(mockFetchSubmission.mock.calls.length).toBeGreaterThanOrEqual(2);

      // A verdict lands on the NEXT load -> polling tears down.
      mockFetchFeedback.mockResolvedValue({
        submission_id: "sub-1",
        feedback: {
          strengths: [],
          weaknesses: [],
          suggestion: "ok",
          verdict: "shortlist",
        },
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      const callsAfterVerdict = mockFetchSubmission.mock.calls.length;

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(mockFetchSubmission.mock.calls.length).toBe(callsAfterVerdict);
    } finally {
      vi.useRealTimers();
    }
  });
});
