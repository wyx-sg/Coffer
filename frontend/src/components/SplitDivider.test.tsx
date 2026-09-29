// src/components/SplitDivider.test.tsx — drag, keyboard, double-click and ARIA of the standalone divider.
import "@/test/pointerEvent";
import { useState } from "react";
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { KEYBOARD_STEP, SplitDivider } from "./SplitDivider";

// The app sidebar's bounds: the divider used on its own beside a pane.
function Harness({ onReset }: { onReset?: () => void }) {
  const [w, setW] = useState(220);
  return (
    <div className="flex">
      <aside data-testid="pane" style={{ width: w }} />
      <SplitDivider
        value={w}
        min={200}
        max={300}
        onChange={setW}
        onReset={onReset ?? (() => setW(220))}
        label="Resize the sidebar"
      />
    </div>
  );
}

const sep = () => screen.getByRole("separator", { name: "Resize the sidebar" });

describe("SplitDivider", () => {
  test("is a focusable vertical separator with its name and px values", () => {
    render(<Harness />);
    const el = sep();
    expect(el).toHaveAttribute("aria-orientation", "vertical");
    expect(el).toHaveAttribute("tabindex", "0");
    expect(el).toHaveAttribute("aria-valuenow", "220");
    expect(el).toHaveAttribute("aria-valuemin", "200");
    expect(el).toHaveAttribute("aria-valuemax", "300");
  });

  // revise-web-ui-ia: web-ui "a divider moves from the keyboard"
  test("→ three times then ← once moves two steps, never past the max", () => {
    render(<Harness />);
    const el = sep();
    el.focus();
    fireEvent.keyDown(el, { key: "ArrowRight" });
    fireEvent.keyDown(el, { key: "ArrowRight" });
    fireEvent.keyDown(el, { key: "ArrowRight" });
    fireEvent.keyDown(el, { key: "ArrowLeft" });
    expect(el).toHaveAttribute("aria-valuenow", String(220 + 2 * KEYBOARD_STEP));
    for (let i = 0; i < 10; i++) fireEvent.keyDown(el, { key: "ArrowRight" });
    expect(el).toHaveAttribute("aria-valuenow", "300");
    for (let i = 0; i < 20; i++) fireEvent.keyDown(el, { key: "ArrowLeft" });
    expect(el).toHaveAttribute("aria-valuenow", "200");
    fireEvent.keyDown(el, { key: "End" });
    expect(el).toHaveAttribute("aria-valuenow", "300");
    fireEvent.keyDown(el, { key: "Home" });
    expect(el).toHaveAttribute("aria-valuenow", "200");
  });

  test("drag moves it with the pointer, clamped, and blocks selection only while dragging", () => {
    render(<Harness />);
    const el = sep();
    fireEvent.pointerDown(el, { button: 0, pointerId: 1, clientX: 220 });
    expect(document.body).toHaveClass("select-none");
    expect(el).toHaveAttribute("data-dragging", "true");
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 260 });
    expect(el).toHaveAttribute("aria-valuenow", "260");
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 900 });
    expect(el).toHaveAttribute("aria-valuenow", "300");
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 0 });
    expect(el).toHaveAttribute("aria-valuenow", "200");
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 0 });
    expect(document.body).not.toHaveClass("select-none");
    expect(el).not.toHaveAttribute("data-dragging");
    // After the drag ends, moving the pointer does nothing.
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 280 });
    expect(el).toHaveAttribute("aria-valuenow", "200");
  });

  test("a non-primary button does not start a drag", () => {
    render(<Harness />);
    const el = sep();
    fireEvent.pointerDown(el, { button: 2, pointerId: 1, clientX: 220 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 260 });
    expect(el).toHaveAttribute("aria-valuenow", "220");
  });

  test("double-click calls onReset", () => {
    const onReset = vi.fn();
    render(<Harness onReset={onReset} />);
    fireEvent.doubleClick(sep());
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  test("an unbounded max leaves aria-valuemax off", () => {
    render(
      <SplitDivider
        value={320}
        min={240}
        max={Number.POSITIVE_INFINITY}
        onChange={() => {}}
        onReset={() => {}}
        label="Resize the list"
      />,
    );
    expect(screen.getByRole("separator")).not.toHaveAttribute("aria-valuemax");
  });
});
