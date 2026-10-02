// frontend/src/lib/reachFilter.test.ts
//
// The filter is an adapter, so what is worth pinning here is that it offers
// the SAME three states, under the SAME labels, that ReachControl's own button
// uses — the two used to carry separate vocabularies ("every"/"selected" vs
// "everywhere"/"restricted") and separate labels for the restricted state.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import { matchesReach, reachFilterOptions } from "./reachFilter";
import { reachLabel, reachModeOf } from "@/lib/reach/reachState";

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
    expect(optionLabel("disabled")).toBe(reachLabel(t, "disabled", null));
    expect(optionLabel("everywhere")).toBe(reachLabel(t, "everywhere", null));
  });
});

describe("matchesReach", () => {
  const off = { enabled: false, scope: null };
  const everyone = { enabled: true, scope: null };
  const some = { enabled: true, scope: { agents: ["u-agent-7f21"] } };

  test("all lets every row through", () => {
    expect([off, everyone, some].every((r) => matchesReach("all", r))).toBe(true);
  });

  test("each state keeps only the rows the control reads as that state", () => {
    expect([off, everyone, some].filter((r) => matchesReach("disabled", r))).toEqual([off]);
    expect([off, everyone, some].filter((r) => matchesReach("everywhere", r))).toEqual([everyone]);
    expect([off, everyone, some].filter((r) => matchesReach("restricted", r))).toEqual([some]);
  });
});
