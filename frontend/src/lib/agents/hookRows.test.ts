// src/lib/agents/hookRows.test.ts — which hooks the Hooks tab lists, and its Event filter.
import { describe, expect, test } from "vitest";

import { filterEvents, hookEntryPath, ownHooks } from "./hookRows";
import { hooksAreFlat } from "./display";
import type { NativeHook } from "@/lib/api/agents";

function hook(over: Partial<NativeHook> = {}): NativeHook {
  return {
    command: "echo hi",
    event: "PreToolUse",
    group_index: 0,
    hook_index: 0,
    matcher: null,
    path: "/home/u/.claude/settings.json",
    plugin: null,
    source: "user",
    timeout: null,
    type: "command",
    ...over,
  };
}

describe("ownHooks", () => {
  test("lists every declared hook, in file order", () => {
    const own = [hook({ event: "Stop" }), hook({ event: "PreToolUse", hook_index: 1 })];
    expect(ownHooks({ items: own, parse_errors: [] })).toEqual(own);
    expect(ownHooks(undefined)).toEqual([]);
  });
});

describe("filterEvents", () => {
  test("offers the six common events, then any other event a file declares", () => {
    const events = filterEvents([hook({ event: "SubagentStop" }), hook({ event: "Stop" })]);
    expect(events.slice(0, 6)).toEqual([
      "SessionStart",
      "UserPromptSubmit",
      "PreToolUse",
      "PostToolUse",
      "Stop",
      "Notification",
    ]);
    expect(events.slice(6)).toEqual(["SubagentStop"]);
  });
});

describe("hookEntryPath", () => {
  test("names a grouped hook by group and hook, and a Cursor hook by its place under the event", () => {
    expect(hookEntryPath(hook({ group_index: 1, hook_index: 2 }))).toBe(
      "hooks.PreToolUse[1].hooks[2]",
    );
    const cursor = hook({ event: "beforeShellExecution", group_index: 3 });
    expect(hookEntryPath(cursor, hooksAreFlat("cursor"))).toBe("hooks.beforeShellExecution[3]");
    expect(hooksAreFlat("codex")).toBe(false);
  });
});
