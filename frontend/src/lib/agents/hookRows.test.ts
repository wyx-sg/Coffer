// src/lib/agents/hookRows.test.ts — the state Coffer's hook reads as, and how long ago it fired.
import { describe, expect, test } from "vitest";

import { cofferHookState, hookNotApproved, timeAgo } from "./hookRows";
import type { CofferHook } from "@/lib/api/agents";

const HOOK: CofferHook = {
  event: "SessionStart",
  path: "/home/u/.codex/hooks.json",
  health: "current",
  trust: "trusted",
  installed_command: "c",
  expected_command: "c",
  last_fired_at: "2026-09-30T10:00:00Z",
};

describe("cofferHookState", () => {
  test("health comes before trust, trust before firing", () => {
    expect(cofferHookState({ ...HOOK, health: "stale", trust: "untrusted" })).toEqual({
      word: "stale",
      tone: "warn",
      repair: true,
    });
    expect(cofferHookState({ ...HOOK, trust: "untrusted", last_fired_at: null }).word).toBe(
      "untrusted",
    );
    expect(cofferHookState({ ...HOOK, last_fired_at: null }).word).toBe("neverFired");
    expect(cofferHookState(HOOK)).toEqual({ word: "current", tone: "ok", repair: false });
  });

  test("an unknown trust makes no claim of its own", () => {
    expect(cofferHookState({ ...HOOK, trust: "unknown" }).word).toBe("current");
  });
});

describe("hookNotApproved", () => {
  test("a current hook the agent has not approved, or approved for another command", () => {
    expect(hookNotApproved({ ...HOOK, trust: "untrusted" })).toBe(true);
    expect(hookNotApproved({ ...HOOK, trust: "modified" })).toBe(true);
    expect(hookNotApproved({ ...HOOK, trust: "trusted" })).toBe(false);
    // Out of date or missing is a repair, not an approval.
    expect(hookNotApproved({ ...HOOK, trust: "untrusted", health: "stale" })).toBe(false);
    expect(hookNotApproved(null)).toBe(false);
  });
});

describe("timeAgo", () => {
  const now = Date.parse("2026-09-30T12:00:00Z");
  test("picks the largest whole unit", () => {
    expect(timeAgo("2026-09-30T10:00:00Z", "en", now)).toBe("2 hours ago");
    expect(timeAgo("2026-09-30T11:46:00Z", "en", now)).toBe("14 minutes ago");
    expect(timeAgo("2026-09-29T12:00:00Z", "en", now)).toBe("yesterday");
    expect(timeAgo("2026-09-30T11:59:50Z", "en", now)).toBe("this minute");
  });
});
