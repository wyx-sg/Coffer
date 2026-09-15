// src/lib/hooks/useMediaQuery.test.ts
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useMediaQuery } from "./useMediaQuery";

type Listener = () => void;

function installMatchMedia(initial: boolean) {
  const listeners = new Set<Listener>();
  const mql = {
    matches: initial,
    addEventListener: (_: string, fn: Listener) => listeners.add(fn),
    removeEventListener: (_: string, fn: Listener) => listeners.delete(fn),
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => mql),
  });
  return {
    set(matches: boolean) {
      mql.matches = matches;
      listeners.forEach((fn) => fn());
    },
  };
}

afterEach(() => {
  // jsdom has no matchMedia; restore that so other tests see the fallback path.
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
});

describe("useMediaQuery", () => {
  test("returns the fallback where matchMedia is unavailable", () => {
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)", true));
    expect(result.current).toBe(true);
  });

  test("tracks the media query and re-renders on change", () => {
    const media = installMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 768px)", true));
    expect(result.current).toBe(false);
    act(() => media.set(true));
    expect(result.current).toBe(true);
  });
});
