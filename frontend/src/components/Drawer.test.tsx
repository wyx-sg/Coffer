// src/components/Drawer.test.tsx — the shared drawer: Esc / ✕ close, ↑ ↓ step, footer.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { Drawer } from "./Drawer";

function setup(extra: Partial<React.ComponentProps<typeof Drawer>> = {}) {
  const onOpenChange = vi.fn();
  const onPrevious = vi.fn();
  const onNext = vi.fn();
  render(
    <Drawer
      open
      onOpenChange={onOpenChange}
      title="sentry__list_issues"
      subtitle="call 8412"
      onPrevious={onPrevious}
      onNext={onNext}
      footer={<button type="button">Open sentry</button>}
      {...extra}
    >
      <input aria-label="filter" />
      <p>body</p>
    </Drawer>,
  );
  return { onOpenChange, onPrevious, onNext };
}

describe("Drawer", () => {
  test("shows title, subtitle, body and footer actions", () => {
    setup();
    expect(screen.getByRole("dialog", { name: "sentry__list_issues" })).toBeInTheDocument();
    expect(screen.getByText("call 8412")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open sentry" })).toBeInTheDocument();
  });

  test("close button and Esc ask to close", () => {
    const { onOpenChange } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    onOpenChange.mockClear();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("previous / next buttons and the arrow keys step, except while typing", () => {
    const { onPrevious, onNext } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onNext).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByText("body"), { key: "ArrowUp" });
    expect(onPrevious).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByLabelText("filter"), { key: "ArrowDown" });
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  test("no stepping props, no step buttons", () => {
    setup({ onPrevious: undefined, onNext: undefined });
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  });
});
