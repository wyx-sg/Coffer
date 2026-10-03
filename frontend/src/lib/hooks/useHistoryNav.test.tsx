import { act, renderHook } from "@testing-library/react";
import { type ReactNode } from "react";
import { BrowserRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, test } from "vitest";

import { useHistoryNav } from "./useHistoryNav";

const wrapper = ({ children }: { children: ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

function useBoth() {
  return { nav: useHistoryNav(), navigate: useNavigate() };
}

describe("useHistoryNav", () => {
  beforeEach(() => window.history.replaceState(null, "", "/"));

  test("tracks where the app's history can go", () => {
    const { result } = renderHook(useBoth, { wrapper });
    expect(result.current.nav.canGoBack).toBe(false);
    expect(result.current.nav.canGoForward).toBe(false);

    act(() => result.current.navigate("/a"));
    expect(result.current.nav.canGoBack).toBe(true);
    expect(result.current.nav.canGoForward).toBe(false);

    act(() => result.current.navigate("/b"));
    expect(window.history.state.idx).toBe(2);
    expect(result.current.nav.canGoBack).toBe(true);
  });

  test("going back opens the forward direction and a new entry closes it", async () => {
    const { result } = renderHook(useBoth, { wrapper });
    act(() => result.current.navigate("/a"));
    act(() => result.current.navigate("/b"));
    await act(async () => {
      window.history.back();
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(result.current.nav.canGoForward).toBe(true);
    expect(result.current.nav.canGoBack).toBe(true);
    act(() => result.current.navigate("/c"));
    expect(result.current.nav.canGoForward).toBe(false);
  });
});
