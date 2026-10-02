// frontend/src/lib/origin.test.tsx — the origin helpers' two page-level hooks.
import { describe, expect, test } from "vitest";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import { useBackLink, useHereOriginState } from "./origin";

function at(path: string, state?: unknown) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter
      initialEntries={[
        {
          pathname: path.split("?")[0],
          search: path.split("?")[1] ? `?${path.split("?")[1]}` : "",
          state,
        },
      ]}
    >
      {children}
    </MemoryRouter>
  );
}

describe("useHereOriginState", () => {
  test.each([
    ["/", "Overview"],
    ["/activity?tab=mcp", "Activity"],
    ["/secrets", "Secrets"],
    ["/agents/claude_code/mcp-servers", "Agents"],
  ])("names %s after its sidebar page", (path, label) => {
    const { result } = renderHook(() => useHereOriginState(), { wrapper: at(path) });
    expect(result.current).toEqual({ from: { to: path, label } });
  });

  test("a page no sidebar entry owns gives no origin", () => {
    const { result } = renderHook(() => useHereOriginState(), { wrapper: at("/nowhere") });
    expect(result.current).toBeUndefined();
  });
});

describe("useBackLink", () => {
  const fallback = { to: "/memory", label: "Memory" };

  test("falls back to the page's own parent", () => {
    const { result } = renderHook(() => useBackLink(fallback), { wrapper: at("/memory/x") });
    expect(result.current).toEqual({ to: "/memory", label: "Back to Memory" });
  });

  test("goes where the reader came from when there is an origin", () => {
    const state = { from: { to: "/secrets", label: "Secrets" } };
    const { result } = renderHook(() => useBackLink(fallback), { wrapper: at("/memory/x", state) });
    expect(result.current).toEqual({ to: "/secrets", label: "Back to Secrets" });
  });
});
