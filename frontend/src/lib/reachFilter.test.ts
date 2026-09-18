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
    expect(reachModeOf({ enabled: false, scope: { agents: ["u-agent-7f21"] } })).toBe("disabled");
  });

  test("an enabled row is unscoped or restricted", () => {
    expect(reachModeOf({ enabled: true, scope: null })).toBe("everywhere");
    expect(reachModeOf({ enabled: true, scope: undefined })).toBe("everywhere");
    expect(reachModeOf({ enabled: true, scope: { agents: ["u-agent-7f21"] } })).toBe("restricted");
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

  test("a kind with no scope gets two choices, not a third that matches nobody", () => {
    // `knowledge` and `memory` declare no per-agent scope, so no row of theirs
    // is ever "restricted" — offering it would be a filter whose only possible
    // effect is to empty the table.
    expect(reachFilterOptions(t, false)).toEqual([
      { value: "disabled", label: "common.disabled" },
      { value: "everywhere", label: "common.enabled" },
    ]);
    // …and under the names the collapsed CONTROL uses, which is the same call
    // its button makes: "Enabled", not "Every agent".
    expect(reachFilterOptions(t, false).map((o) => o.label)).toEqual([
      reachLabel(t, "disabled", false, null),
      reachLabel(t, "everywhere", false, null),
    ]);
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

  test("with no scope it is headed Status and places every enabled row alike", () => {
    const filter = reachFilter(
      t,
      (row: { on: boolean; scope: { agents: string[] } | null }) => ({
        enabled: row.on,
        scope: row.scope,
      }),
      false,
    );
    expect(filter.label).toBe("resources.cols.status");
    expect(filter.accessor({ on: true, scope: null })).toBe("everywhere");
    expect(filter.accessor({ on: false, scope: null })).toBe("disabled");
    // A scope left in the payload from when the kind had one does not put the
    // row in a state the filter no longer offers — it would be unreachable
    // under either choice.
    expect(filter.accessor({ on: true, scope: { agents: ["u-agent-7f21"] } })).toBe("everywhere");
    expect(filter.accessor({ on: false, scope: { agents: ["u-agent-7f21"] } })).toBe("disabled");
  });
});
