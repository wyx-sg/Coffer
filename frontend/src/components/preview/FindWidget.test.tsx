// src/components/preview/FindWidget.test.tsx
import { type ComponentProps } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FindWidget } from "./FindWidget";

function setup(overrides: Partial<ComponentProps<typeof FindWidget>> = {}) {
  const props = {
    query: "",
    count: 0,
    active: -1,
    caseSensitive: false,
    onQueryChange: vi.fn(),
    onToggleCase: vi.fn(),
    onNext: vi.fn(),
    onPrev: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<FindWidget {...props} />);
  return props;
}

describe("FindWidget", () => {
  test("typing reports the new query", () => {
    const props = setup();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "abc" } });
    expect(props.onQueryChange).toHaveBeenCalledWith("abc");
  });

  test("shows active/total when there are matches", () => {
    setup({ query: "foo", count: 3, active: 1 });
    expect(screen.getByText("2/3")).toBeInTheDocument();
  });

  test("shows a no-matches message when the query finds nothing", () => {
    setup({ query: "zzz", count: 0, active: -1 });
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });

  test("next / prev buttons are disabled with no matches", () => {
    setup({ query: "zzz", count: 0 });
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });

  test("Enter steps forward, Shift+Enter steps back, Escape closes", () => {
    const props = setup({ query: "foo", count: 2, active: 0 });
    const input = screen.getByRole("textbox");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(props.onNext).toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(props.onPrev).toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(props.onClose).toHaveBeenCalled();
  });

  test("the case-sensitivity toggle reflects and reports state", () => {
    const props = setup({ caseSensitive: true });
    const toggle = screen.getByRole("button", { name: /case sensitive/i });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(toggle);
    expect(props.onToggleCase).toHaveBeenCalled();
  });
});
