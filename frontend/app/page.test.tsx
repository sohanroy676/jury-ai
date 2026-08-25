import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "./page";

// NavLinks imports next/link, which jsdom does not support; the link
// bar is not the subject of these upload-form tests.
vi.mock("../components/NavLinks", () => ({ default: () => null }));

vi.mock("../lib/api", () => {
  class FakeApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }
  return {
    ApiError: FakeApiError,
    fetchSubmission: vi.fn(),
    fetchSubmissions: vi.fn(),
    uploadSubmission: vi.fn(),
  };
});

import * as api from "../lib/api";

const mockFetchSubmissions = api.fetchSubmissions as ReturnType<typeof vi.fn>;
const mockFetchSubmission = api.fetchSubmission as ReturnType<typeof vi.fn>;
const mockUpload = api.uploadSubmission as ReturnType<typeof vi.fn>;

function pdfFile(size = 1024, name = "proposal.pdf"): File {
  const file = new File(["pdf-bytes"], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText(/Team name/i), {
    target: { value: "Team Alpha" },
  });
  fireEvent.change(screen.getByLabelText(/Submission file/i), {
    target: { files: [pdfFile()] },
  });
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: /submit/i }) as HTMLButtonElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchSubmissions.mockResolvedValue([]);
});

describe("Home portal", () => {
  it("renders heading, inputs, and keeps submit disabled until valid", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { name: /JuryAI Submission Portal/i })
    ).toBeTruthy();
    expect(screen.getByLabelText(/Team name/i)).toBeTruthy();
    expect(
      screen.getByLabelText(/Submission file/i).getAttribute("accept")
    ).toBe(".pdf,.pptx");

    expect(submitButton().disabled).toBe(true);
    expect(
      screen.getByText(/A team name and a valid PDF\/PPTX file are required/i)
    ).toBeTruthy();
  });

  it("flags an oversized file inline BEFORE submit and blocks sending", () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/Team name/i), {
      target: { value: "Team Alpha" },
    });
    fireEvent.change(screen.getByLabelText(/Submission file/i), {
      target: { files: [pdfFile(51 * 1024 * 1024)] },
    });

    expect(
      screen.getByText(
        /File too large \(51\.0 MB\)\. The maximum size is 50 MB\./i
      )
    ).toBeTruthy();
    expect(submitButton().disabled).toBe(true);
    expect(mockUpload).not.toHaveBeenCalled();
  });

  it("flags an unsupported extension inline before submit", () => {
    render(<Home />);
    fireEvent.change(screen.getByLabelText(/Team name/i), {
      target: { value: "Team Alpha" },
    });
    fireEvent.change(screen.getByLabelText(/Submission file/i), {
      target: { files: [pdfFile(1024, "virus.exe")] },
    });

    expect(screen.getByText(/Unsupported file type "\.exe"/i)).toBeTruthy();
    expect(mockUpload).not.toHaveBeenCalled();
  });

  it("uploads successfully and lists the parsed section titles", async () => {
    mockUpload.mockResolvedValue({
      id: "sub-9",
      team_name: "Team Alpha",
      status: "submitted",
    });
    mockFetchSubmission.mockResolvedValue({
      submission: { id: "sub-9", team_name: "Team Alpha" },
      parsed: {
        raw_text: "...",
        source_format: "pdf",
        sections: [{ title: "Problem Statement" }, { title: "Solution" }],
      },
      scores: [],
    });

    render(<Home />);
    fillValidForm();
    fireEvent.click(submitButton());

    await screen.findByText(
      /Parsed sections \(2\): Problem Statement, Solution\./i
    );
    expect(mockUpload).toHaveBeenCalledWith("Team Alpha", expect.any(File), {
      replaceExisting: false,
    });
    expect(mockFetchSubmission).toHaveBeenCalledWith("sub-9");
  });

  it("offers replace on 409 and retries with replaceExisting=true", async () => {
    mockUpload
      .mockRejectedValueOnce(
        new api.ApiError(
          409,
          "Team 'Team Alpha' already has an active submission (uploaded 2026-08-25). Confirm below to replace it - the previous version is kept in history."
        )
      )
      .mockResolvedValueOnce({ id: "sub-10", team_name: "Team Alpha" });
    mockFetchSubmission.mockResolvedValue({
      submission: { id: "sub-10", team_name: "Team Alpha" },
      parsed: { raw_text: "...", source_format: "pdf", sections: [] },
      scores: [],
    });

    render(<Home />);
    fillValidForm();
    fireEvent.click(submitButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("already has an active submission");

    fireEvent.click(
      screen.getByRole("button", { name: /replace previous submission/i })
    );

    await waitForReplaceCall();
    await screen.findByText(/No titled sections were detected/i);
  });

  it("maps network failures to the friendly message", async () => {
    mockUpload.mockRejectedValue(
      new api.ApiError(0, "Network error — could not reach the backend.")
    );
    render(<Home />);
    fillValidForm();
    fireEvent.click(submitButton());
    await screen.findByText(/Network error — could not reach the backend\./i);
  });
});

async function waitForReplaceCall() {
  await vi.waitFor(() =>
    expect(mockUpload).toHaveBeenLastCalledWith(
      "Team Alpha",
      expect.any(File),
      { replaceExisting: true }
    )
  );
}
