// frontend/src/components/ui/toast.test.tsx
//
// The toast queue: useToast() surfaces failures/confirmations through the stack
// rendered by the ToastProvider. Error toasts are role="alert" so a failed
// mutation is announced rather than silent. Outside a provider, useToast()
// returns a safe no-op so isolated components don't throw. The timing rules
// (5s, 8s with Undo, errors stay, hover pauses) and the three-card cap are
// pinned with fake timers.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { useRef } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";

import { ToastProvider, useToast, type ToastOptions } from "./toast";

type Kind = "error" | "success" | "info";

function Trigger({
  kind = "error",
  message = "delete failed",
  options,
}: {
  kind?: Kind;
  message?: string;
  options?: ToastOptions;
}) {
  const { toast } = useToast();
  return (
    <button type="button" onClick={() => toast[kind](message, options)}>
      go
    </button>
  );
}

function fire(n = 1) {
  for (let i = 0; i < n; i++) fireEvent.click(screen.getByRole("button", { name: "go" }));
}

describe("toast", () => {
  test("an error toast renders with role=alert and is dismissible", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fire();
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

  test("an error with no action offers Details, which shows the rest", () => {
    render(
      <ToastProvider>
        <Trigger options={{ details: "The daemon answered 409." }} />
      </ToastProvider>,
    );
    fire();
    expect(screen.queryByText("The daemon answered 409.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText("The daemon answered 409.")).toBeInTheDocument();
  });

  test("an error with a Retry offers it, and clicking it retries and dismisses", () => {
    const retry = vi.fn();
    render(
      <ToastProvider>
        <Trigger options={{ retry }} />
      </ToastProvider>,
    );
    fire();
    expect(screen.queryByRole("button", { name: "Details" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("an action runs and dismisses its toast", () => {
    const open = vi.fn();
    render(
      <ToastProvider>
        <Trigger
          kind="success"
          message="Added MCP server smart"
          options={{ action: { label: "Open", onClick: open } }}
        />
      </ToastProvider>,
    );
    fire();
    expect(screen.getByRole("status")).toHaveTextContent("Added MCP server smart");
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(open).toHaveBeenCalledOnce();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("toast timing", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

  test("success and info leave after 5s", () => {
    render(
      <ToastProvider>
        <Trigger kind="success" message="Saved" />
      </ToastProvider>,
    );
    fire();
    advance(4900);
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    advance(200);
    expect(screen.queryByRole("status")).toBeNull();
  });

  test("a toast carrying Undo stays 8s", () => {
    render(
      <ToastProvider>
        <Trigger kind="info" message="Turned off postgres" options={{ undo: () => {} }} />
      </ToastProvider>,
    );
    fire();
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    advance(7900);
    expect(screen.getByRole("status")).toBeInTheDocument();
    advance(200);
    expect(screen.queryByRole("status")).toBeNull();
  });

  test("an error stays 8s, then leaves on its own", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    fire();
    advance(7_000);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    advance(1_500);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("hovering a card pauses its clock; leaving resumes it with the time left", () => {
    render(
      <ToastProvider>
        <Trigger kind="success" message="Saved" />
      </ToastProvider>,
    );
    fire();
    advance(3000);
    fireEvent.mouseEnter(screen.getByRole("status"));
    advance(10_000);
    expect(screen.getByRole("status")).toBeInTheDocument();
    fireEvent.mouseLeave(screen.getByRole("status"));
    advance(1900);
    expect(screen.getByRole("status")).toBeInTheDocument();
    advance(200);
    expect(screen.queryByRole("status")).toBeNull();
  });

  test("focus inside a card pauses it too", () => {
    render(
      <ToastProvider>
        <Trigger
          kind="success"
          message="Saved"
          options={{ action: { label: "Open", onClick() {} } }}
        />
      </ToastProvider>,
    );
    fire();
    fireEvent.focus(screen.getByRole("button", { name: "Open" }));
    advance(10_000);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  test("a card that leaves on its own draws a timer line", () => {
    render(
      <ToastProvider>
        <Trigger kind="success" message="Saved" />
      </ToastProvider>,
    );
    fire();
    expect(screen.getByTestId("toast-timer")).toBeInTheDocument();
  });

  test("an error draws a timer line too", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    fire();
    expect(screen.getByTestId("toast-timer")).toBeInTheDocument();
  });

  test("at most three show, newest at the bottom; older ones fold into a chip", () => {
    function Numbered() {
      const { toast } = useToast();
      const n = useRef(0);
      return (
        <button type="button" onClick={() => toast.error(`failure ${++n.current}`)}>
          go
        </button>
      );
    }
    render(
      <ToastProvider>
        <Numbered />
      </ToastProvider>,
    );
    fire(5);
    const texts = () => screen.getAllByRole("alert").map((el) => el.textContent);
    expect(texts()).toHaveLength(3);
    expect(texts()[2]).toContain("failure 5");
    expect(texts()[0]).toContain("failure 3");
    fireEvent.click(screen.getByRole("button", { name: "2 more" }));
    expect(texts()).toHaveLength(5);
    expect(texts()[0]).toContain("failure 1");
  });
});
