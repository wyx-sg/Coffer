import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, test } from "vitest";

import { useSearchParamsKeepingState } from "./useSearchParamsKeepingState";

describe("useSearchParamsKeepingState", () => {
  test("changing a param keeps the history state (the router state)", () => {
    const state = { opened: "elsewhere" };
    const { result } = renderHook(
      () => ({ set: useSearchParamsKeepingState()[1], loc: useLocation() }),
      {
        wrapper: ({ children }) => (
          <MemoryRouter initialEntries={[{ pathname: "/skills/a", state }]}>
            {children}
          </MemoryRouter>
        ),
      },
    );
    act(() => result.current.set({ file: "SKILL.md" }, { replace: true }));
    expect(result.current.loc.search).toBe("?file=SKILL.md");
    expect(result.current.loc.state).toEqual(state);
  });
});
