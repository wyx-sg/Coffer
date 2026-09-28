// HelpTip: the "?" that holds a surface's explanation. It must be reachable
// by every input a reader has — a click (which is also Enter / Space on a
// button), a hover, and Escape to put it away — and it must have a name, since
// an icon alone says nothing to a screen reader.
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { HelpTip } from "./HelpTip";

afterEach(() => {
  vi.useRealTimers();
});

describe("HelpTip", () => {
  test("has an accessible name, and a click shows the explanation", () => {
    render(<HelpTip>Rebinding needs no restart.</HelpTip>);

    const button = screen.getByRole("button", { name: /more info/i });
    expect(screen.queryByText("Rebinding needs no restart.")).not.toBeInTheDocument();

    fireEvent.click(button);
    expect(screen.getByText("Rebinding needs no restart.")).toBeInTheDocument();
  });

  test("a second click closes a pinned tip, and so does Escape", () => {
    render(<HelpTip label="About pairing">Re-pairing replaces the owner.</HelpTip>);
    const button = screen.getByRole("button", { name: "About pairing" });

    fireEvent.click(button);
    fireEvent.click(button);
    expect(screen.queryByText("Re-pairing replaces the owner.")).not.toBeInTheDocument();

    fireEvent.click(button);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.queryByText("Re-pairing replaces the owner.")).not.toBeInTheDocument();
  });

  test("hovering opens it after a short delay, and leaving closes it", () => {
    vi.useFakeTimers();
    render(<HelpTip>Shown on hover.</HelpTip>);
    const button = screen.getByRole("button", { name: /more info/i });

    fireEvent.pointerEnter(button);
    expect(screen.queryByText("Shown on hover.")).not.toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Shown on hover.")).toBeInTheDocument();

    fireEvent.pointerLeave(button);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.queryByText("Shown on hover.")).not.toBeInTheDocument();
  });

  test("a click after a hover pins the tip rather than closing it", () => {
    vi.useFakeTimers();
    render(<HelpTip>Pinned.</HelpTip>);
    const button = screen.getByRole("button", { name: /more info/i });

    fireEvent.pointerEnter(button);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    fireEvent.click(button);
    fireEvent.pointerLeave(button);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Pinned.")).toBeInTheDocument();
  });
});
