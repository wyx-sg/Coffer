// src/components/RelativeTime.test.tsx — relative text in the page, exact time on hover.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import { RelativeTime } from "./RelativeTime";

describe("RelativeTime", () => {
  // Midday, so "5 min ago" never crosses midnight into a dated label.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 3, 12, 0, 0));
  });
  afterEach(() => vi.useRealTimers());

  test("a recent time reads relative and carries the exact time as dateTime", () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString();
    render(<RelativeTime iso={iso} />);
    expect(screen.getByText("5 min ago")).toHaveAttribute("datetime", iso);
  });

  test("hover shows the exact local time", async () => {
    render(<RelativeTime iso={new Date(2020, 0, 5, 9, 41, 7)} />);
    await act(async () => {
      act(() => screen.getByText("Jan 5, 2020").focus());
    });
    expect((await screen.findAllByText("Jan 5, 2020 at 09:41:07")).length).toBeGreaterThan(0);
  });
});
