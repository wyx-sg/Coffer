// frontend/src/lib/reachFilter.test.ts
//
// The filter is an adapter, so what is worth pinning here is that it offers
// the SAME three states, under the SAME labels, that ReachControl's own button
// uses — the two used to carry separate vocabularies ("every"/"selected" vs
// "everywhere"/"restricted") and separate labels for the restricted state.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import { reachFilter, reachFilterOptions } from "./reachFilter";
import { reachLabel, reachModeOf } from "@/components/reach/reachState";

// Echoes the key, so the assertions read which label each choice carries.
const t = ((key: string) => key) as unknown as TFunction;

describe("reachModeOf", () => {
  test("disabled beats scope", () => {
    expect(reachModeOf({ enabled: false, scope: null })).toBe("disabled");
    expect(reachModeOf({ enabled: false, scope: { agents: ["cc"] } })).toBe("disabled");
  });

  test("an enabled row is unscoped or restricted", () => {
    expect(reachModeOf({ enabled: true, scope: null })).toBe("everywhere");
    expect(reachModeOf({ enabled: true, scope: undefined })).toBe("everywhere");
    expect(reachModeOf({ enabled: true, scope: { agents: ["cc"] } })).toBe("restricted");
    // An empty agent list is still a restriction (it names nobody).
    expect(reachModeOf({ enabled: true, scope: { agents: [] } })).toBe("restricted");
  });
});

describe("reachFilterOptions", () => {
  test("offers the three states ReachControl shows, in its order", () => {
    expect(reachFilterOptions(t)).toEqual([
      { value: "disabled", label: "common.disabled" },
      { value: "everywhere", label: "scope.everywhere" },
      { value: "restricted", label: "scope.restricted" },
    ]);
  });

  test("labels each state exactly as the control's own button does", () => {
    const optionLabel = (mode: string) =>
      reachFilterOptions(t).find((o) => o.value === mode)?.label;
    // The control can count agents where it has a row in hand; for the states
    // it cannot count, its text and the filter option must be the same string.
    expect(optionLabel("disabled")).toBe(reachLabel(t, "disabled", true, null));
    expect(optionLabel("everywhere")).toBe(reachLabel(t, "everywhere", true, null));
  });
});

describe("reachFilter", () => {
  test("builds a DataTable filter under the shared Reach header", () => {
    const filter = reachFilter(t, (row: { on: boolean }) => ({ enabled: row.on, scope: null }));
    expect(filter.key).toBe("reach");
    expect(filter.label).toBe("resources.cols.reach");
    expect(filter.allLabel).toBe("resources.status.all");
    expect(filter.accessor({ on: true })).toBe("everywhere");
    expect(filter.accessor({ on: false })).toBe("disabled");
  });
});
