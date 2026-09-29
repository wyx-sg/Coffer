// src/lib/hooks/useResizableWidth.test.ts — clamp helper and the remembered, clamped width.
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { blockLocalStorage } from "@/test/blockedStorage";

import { clampWidth, useResizableWidth } from "./useResizableWidth";

const opts = { storageKey: "test.pane", defaultWidth: 320, min: 240, max: 600 };

beforeEach(() => window.localStorage.clear());
afterEach(() => window.localStorage.clear());

describe("clampWidth", () => {
  test("keeps a value inside the bounds and rounds it", () => {
    expect(clampWidth(300.4, 240, 600)).toBe(300);
    expect(clampWidth(100, 240, 600)).toBe(240);
    expect(clampWidth(900, 240, 600)).toBe(600);
  });

  test("the lower bound wins when the bounds cross", () => {
    expect(clampWidth(300, 240, 120)).toBe(240);
  });

  test("an unbounded max and a non-finite value", () => {
    expect(clampWidth(5000, 240, Number.POSITIVE_INFINITY)).toBe(5000);
    expect(clampWidth(Number.NaN, 240, 600)).toBe(240);
  });
});

describe("useResizableWidth", () => {
  test("opens at the default with nothing stored", () => {
    const { result } = renderHook(() => useResizableWidth(opts));
    expect(result.current.width).toBe(320);
    expect(result.current.bounds).toEqual({ min: 240, max: 600 });
  });

  test("setWidth clamps, persists, and a remount reads it back", () => {
    const { result, unmount } = renderHook(() => useResizableWidth(opts));
    act(() => result.current.setWidth(9999));
    expect(result.current.width).toBe(600);
    expect(window.localStorage.getItem("coffer.split.test.pane")).toBe("600");
    unmount();
    const again = renderHook(() => useResizableWidth(opts));
    expect(again.result.current.width).toBe(600);
    // Another split is untouched.
    const other = renderHook(() => useResizableWidth({ ...opts, storageKey: "other" }));
    expect(other.result.current.width).toBe(320);
  });

  test("a remembered width is clamped on read against the current bounds", () => {
    window.localStorage.setItem("coffer.split.test.pane", "900");
    const { result, rerender } = renderHook((p) => useResizableWidth(p), {
      initialProps: { ...opts, max: 500 },
    });
    expect(result.current.width).toBe(500);
    // The container grows back: the width it was asked for returns.
    rerender({ ...opts, max: 1000 });
    expect(result.current.width).toBe(900);
  });

  test("a garbage stored value falls back to the default", () => {
    window.localStorage.setItem("coffer.split.test.pane", "wide");
    const { result } = renderHook(() => useResizableWidth(opts));
    expect(result.current.width).toBe(320);
  });

  test("reset returns to the default and forgets the stored width", () => {
    const { result } = renderHook(() => useResizableWidth(opts));
    act(() => result.current.setWidth(500));
    act(() => result.current.reset());
    expect(result.current.width).toBe(320);
    expect(window.localStorage.getItem("coffer.split.test.pane")).toBeNull();
  });

  // revise-web-ui-ia: web-ui "no stored width falls back to the default"
  test.each(["methods", "access"] as const)(
    "blocked storage (%s) → default, still settable",
    (mode) => {
      const restore = blockLocalStorage(mode);
      try {
        const { result } = renderHook(() => useResizableWidth(opts));
        expect(result.current.width).toBe(320);
        act(() => result.current.setWidth(400));
        expect(result.current.width).toBe(400);
        act(() => result.current.reset());
        expect(result.current.width).toBe(320);
      } finally {
        restore();
      }
    },
  );
});
