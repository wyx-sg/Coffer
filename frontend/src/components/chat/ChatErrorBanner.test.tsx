// frontend/src/components/chat/ChatErrorBanner.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ChatErrorBanner } from "./ChatErrorBanner";

describe("ChatErrorBanner", () => {
  test("announces the message as an alert", () => {
    render(<ChatErrorBanner message="provider failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("provider failed");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("Retry and Dismiss call back only when provided", () => {
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(<ChatErrorBanner message="x" onRetry={onRetry} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
