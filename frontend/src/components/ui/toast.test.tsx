// frontend/src/components/ui/toast.test.tsx
//
// The minimal toast system: useToast() surfaces failures/confirmations through a
// <Toaster/> rendered by the ToastProvider. Error toasts are role="alert" so a
// failed mutation is announced rather than silent (FE1/FE2/SW3). Outside a
// provider, useToast() returns a safe no-op so isolated components don't throw.
import { describe, expect, test } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

import { ToastProvider, useToast } from "./toast";

function Trigger() {
  const { toast } = useToast();
  return (
    <button type="button" onClick={() => toast.error("delete failed")}>
      go
    </button>
  );
}

describe("toast", () => {
  test("an error toast renders with role=alert and is dismissible", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "go" }));
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("delete failed");

    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("useToast() is a safe no-op when no provider is mounted", () => {
    // Rendering Trigger without a provider must not throw; clicking is a no-op.
    render(<Trigger />);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "go" }));
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
