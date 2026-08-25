import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ErrorBanner from "./ErrorBanner";

describe("ErrorBanner", () => {
  it("renders nothing when the message is null", () => {
    const { container } = render(<ErrorBanner message={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the message with role=alert", () => {
    render(<ErrorBanner message="Something broke." />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Something broke."
    );
  });

  it("calls onDismiss when the dismiss button is clicked", () => {
    const onDismiss = vi.fn();
    render(<ErrorBanner message="Boom" onDismiss={onDismiss} />);

    fireEvent.click(screen.getByRole("button", { name: /dismiss error/i }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
