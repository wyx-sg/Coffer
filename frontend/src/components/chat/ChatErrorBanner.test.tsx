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

  test("the reply variant puts the explanation under the message, with Retry and Dismiss", () => {
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(
      <ChatErrorBanner
        variant="reply"
        message="The turn failed: 529"
        detail="Retry sends the same message again."
        onRetry={onRetry}
        onDismiss={onDismiss}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The turn failed: 529");
    expect(alert).toHaveTextContent("Retry sends the same message again.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  test("the reply variant can name its action Resume queue", () => {
    render(
      <ChatErrorBanner variant="reply" message="x" onRetry={vi.fn()} retryLabel="Resume queue" />,
    );
    expect(screen.getByRole("button", { name: "Resume queue" })).toBeInTheDocument();
  });
});
