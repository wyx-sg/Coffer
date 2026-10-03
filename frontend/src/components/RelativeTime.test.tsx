// src/components/RelativeTime.test.tsx — relative text in the page, exact time on hover.
import { describe, expect, test } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { RelativeTime } from "./RelativeTime";

describe("RelativeTime", () => {
  test("a recent time reads relative and carries the exact time as dateTime", () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString();
    render(<RelativeTime iso={iso} />);
    expect(screen.getByText("5 min ago")).toHaveAttribute("datetime", iso);
  });

  test("hover shows the exact local time", async () => {
    render(<RelativeTime iso={new Date(2020, 0, 5, 9, 41, 7)} />);
    await act(async () => {
      fireEvent.focus(screen.getByText("Jan 5, 2020"));
    });
    expect((await screen.findAllByText("Jan 5, 2020 at 09:41:07")).length).toBeGreaterThan(0);
  });
});
