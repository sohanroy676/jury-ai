import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("Home", () => {
  it("renders the submission portal heading", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { name: /JuryAI Submission Portal/i })
    ).toBeTruthy();
  });

  it("renders the team name input", () => {
    render(<Home />);
    expect(screen.getByLabelText(/Team name/i)).toBeTruthy();
  });

  it("renders the file input with pdf/pptx accept", () => {
    render(<Home />);
    const fileInput = screen.getByLabelText(/Submission file/i);
    expect(fileInput).toBeTruthy();
    expect(fileInput.getAttribute("accept")).toBe(".pdf,.pptx");
  });
});
