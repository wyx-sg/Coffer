// frontend/src/lib/syncRoundToast.test.ts
//
// A finished round's toast says what actually happened: a round that stopped,
// failed, was held or is waiting to join is not a "success".
import { describe, expect, test } from "vitest";
import i18next from "@/i18n";
import type { TFunction } from "i18next";

import type { ConvergeRound, RoundStatus } from "@/lib/api/sync";
import { roundToast } from "./syncRoundToast";

const t = i18next.t.bind(i18next) as TFunction;
const NO_COUNTS = { added: 0, modified: 0, deleted: 0, changes: [] };

function round(status: RoundStatus, over: Partial<ConvergeRound> = {}): ConvergeRound {
  return {
    status,
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: null,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    not_applicable: [],
    locked_refs: [],
    pending: null,
    join_report: null,
    error: null,
    ...over,
  };
}

describe("roundToast", () => {
  test("a round that converged is a success naming what it moved", () => {
    const toast = roundToast(t, round("ok"));
    expect(toast.variant).toBe("success");
    expect(toast.message).toMatch(/converged/);
  });

  test.each([
    ["conflict", "error", /conflict/i],
    ["push_failed", "error", /could not reach the remote/i],
    ["awaiting_confirmation", "info", /held for your confirmation/i],
    ["awaiting_join", "info", /has not joined this remote yet/i],
  ] as const)("%s is not reported as a success", (status, variant, message) => {
    const toast = roundToast(t, round(status));
    expect(toast.variant).toBe(variant);
    expect(toast.message).toMatch(message);
  });

  test("a failed round carries its own error", () => {
    const toast = roundToast(t, round("failed", { error: "remote unreachable" }));
    expect(toast.variant).toBe("error");
    expect(toast.message).toMatch(/remote unreachable/);
  });
});
