import { act, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/i18n";
import { ShowAllRow } from "./LongList";
import { useLongList } from "./useLongList";

const rows = (n: number) => Array.from({ length: n }, (_, i) => i);

describe("useLongList", () => {
  it("shows five rows and expands in place", () => {
    const { result } = renderHook(() => useLongList(rows(12)));
    expect(result.current.visible).toHaveLength(5);
    expect(result.current.collapsed).toBe(true);
    act(() => result.current.expand());
    expect(result.current.visible).toHaveLength(12);
    expect(result.current.collapsed).toBe(false);
  });

  it("does not collapse a short list and scrolls inside only once expanded", () => {
    const short = renderHook(() => useLongList(rows(5)));
    expect(short.result.current.collapsed).toBe(false);
    const { result } = renderHook(() => useLongList(rows(9), { scrollInside: true }));
    expect(result.current.listClassName).toBe("");
    act(() => result.current.expand());
    expect(result.current.listClassName).toContain("overflow-y-auto");
  });
});

describe("ShowAllRow", () => {
  it("says how many are shown and offers Show all", () => {
    render(<ShowAllRow shown={5} total={12} onShowAll={() => {}} />);
    expect(screen.getByText("Showing 5 of 12")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show all" })).toBeInTheDocument();
  });
});
