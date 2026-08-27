import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppealsQueueView from "./AppealsQueueView";

vi.mock("../lib/api", () => ({
  ApiError: class FakeApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  fetchAppeals: vi.fn(),
  resolveAppeal: vi.fn(),
}));

vi.mock("./NavLinks", () => ({ default: () => null }));

import * as api from "../lib/api";

const mockFetchAppeals = api.fetchAppeals as ReturnType<typeof vi.fn>;
const mockResolveAppeal = api.resolveAppeal as ReturnType<typeof vi.fn>;

const SAMPLE_APPEALS = [
  {
    id: "appeal-1",
    submission_id: "sub-1",
    hackathon_id: "default",
    reason: "Score was too low.",
    status: "open",
    decision: null,
    decision_note: "",
    evaluator: "",
    created_at: "2026-08-27T00:00:00Z",
    decided_at: null,
    context: {
      team_name: "Team Alpha",
      composite_score: 82.5,
      rank: 3,
      shortlisted: false,
      scores: [
        { criterion: "problem_fit", score: 8, justification: "Clear problem." },
      ],
      feedback: {
        verdict: "reject",
        strengths: ["Good idea"],
        weaknesses: ["Poor execution"],
        suggestion: "Add a demo.",
      },
    },
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AppealsQueueView", () => {
  it("shows a loading placeholder while fetching", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    mockFetchAppeals.mockReturnValue(
      new Promise((res) => {
        resolveFetch = res;
      })
    );

    render(<AppealsQueueView />);
    expect(screen.getByText(/Loading appeals/i)).toBeTruthy();

    resolveFetch({ appeals: [] });
    await waitFor(() => expect(mockFetchAppeals).toHaveBeenCalled());
  });

  it("shows empty state when no open appeals exist", async () => {
    mockFetchAppeals.mockResolvedValue({ appeals: [] });

    render(<AppealsQueueView />);
    await waitFor(() =>
      expect(screen.getByText(/No open appeals/i)).toBeTruthy()
    );
  });

  it("renders an open appeal with its original AI context", async () => {
    mockFetchAppeals.mockResolvedValue({ appeals: SAMPLE_APPEALS });

    render(<AppealsQueueView />);

    await waitFor(() =>
      expect(screen.getByText("Appeals queue")).toBeTruthy()
    );

    // The appeal's reason appears
    expect(screen.getByText(/Score was too low/i)).toBeTruthy();
    // The original AI verdict is attached
    expect(screen.getByText("reject")).toBeTruthy();
    // The team name is visible
    expect(screen.getByText(/Team Alpha/i)).toBeTruthy();
  });

  it("requires an evaluator name before resolving", async () => {
    mockFetchAppeals.mockResolvedValue({ appeals: SAMPLE_APPEALS });
    mockResolveAppeal.mockRejectedValue(
      new api.ApiError(422, "Evaluator identity is required.")
    );

    render(<AppealsQueueView />);

    await waitFor(() =>
      expect(screen.getByText("Appeals queue")).toBeTruthy()
    );

    // Leave evaluator field empty, click "Upheld"
    fireEvent.click(screen.getByRole("button", { name: /Upheld/i }));

    await waitFor(() =>
      expect(screen.getByText(/evaluator name before resolving/i)).toBeTruthy()
    );

    expect(mockResolveAppeal).not.toHaveBeenCalled();
  });

  it("calls resolveAppeal with the evaluator name when resolving an open appeal", async () => {
    mockFetchAppeals.mockResolvedValue({ appeals: SAMPLE_APPEALS });
    mockResolveAppeal.mockResolvedValue({
      appeal: { ...SAMPLE_APPEALS[0], status: "resolved", decision: "upheld" },
      notification: { appeal_email: { status: "sent", reason: "" } },
    });

    render(<AppealsQueueView />);

    await waitFor(() =>
      expect(screen.getByText("Appeals queue")).toBeTruthy()
    );

    // Type an evaluator name
    fireEvent.change(screen.getByLabelText(/Evaluator name/i), {
      target: { value: "e-1" },
    });

    // Click the "Dismissed" button
    fireEvent.click(screen.getByRole("button", { name: /Dismissed/i }));

    await waitFor(() =>
      expect(mockResolveAppeal).toHaveBeenCalledWith("appeal-1", {
        decision: "dismissed",
        decisionNote: "",
        evaluator: "e-1",
      })
    );
  });

  it("shows an error banner when fetch fails", async () => {
    mockFetchAppeals.mockRejectedValue(
      new api.ApiError(503, "Supabase credentials are missing.")
    );

    render(<AppealsQueueView />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toBeTruthy()
    );
    expect(screen.getByText(/Supabase credentials are missing/i)).toBeTruthy();
  });
});
