// frontend/src/lib/reachFilter.test.ts
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import { reachFilter, reachFilterOptions, reachState } from "./reachFilter";

// Echoes the key, so the assertions read which label each choice carries.
const t = ((key: string) => key) as unknown as TFunction;

describe("reachState", () => {
  test("disabled beats scope", () => {
    expect(reachState({ enabled: false, scope: null })).toBe("disabled");
    expect(reachState({ enabled: false, scope: { agents: ["cc"] } })).toBe("disabled");
  });

  test("an enabled row is unscoped or restricted", () => {
    expect(reachState({ enabled: true, scope: null })).toBe("every");
    expect(reachState({ enabled: true, scope: undefined })).toBe("every");
    expect(reachState({ enabled: true, scope: { agents: ["cc"] } })).toBe("selected");
    // An empty agent list is still a restriction (it names nobody).
    expect(reachState({ enabled: true, scope: { agents: [] } })).toBe("selected");
  });
});

describe("reachFilterOptions", () => {
  test("offers the three states ScopeControl shows, in its order", () => {
    expect(reachFilterOptions(t)).toEqual([
      { value: "disabled", label: "common.disabled" },
      { value: "every", label: "scope.everywhere" },
      { value: "selected", label: "scope.restricted" },
    ]);
  });
});

describe("reachFilter", () => {
  test("builds a DataTable filter under the shared Reach header", () => {
    const filter = reachFilter(t, (row: { on: boolean }) => ({ enabled: row.on, scope: null }));
    expect(filter.key).toBe("reach");
    expect(filter.label).toBe("resources.cols.reach");
    expect(filter.allLabel).toBe("resources.status.all");
    expect(filter.accessor({ on: true })).toBe("every");
    expect(filter.accessor({ on: false })).toBe("disabled");
  });
});
