// src/lib/agents/counts.test.ts — the per-kind counts, and who a resource reaches.
import { describe, expect, test } from "vitest";

import type { AgentHooksOut, McpEntryOut, PluginOut } from "@/lib/api/agents";
import { hookCounts, mcpCounts, pluginCounts, reachesAgent, skillCounts } from "./counts";
import { countByOwner, filterByOwner, parseOwnerFilter } from "./owner";

describe("reachesAgent", () => {
  test("a switched-off resource reaches nobody; an unscoped one every agent; a scoped one its list", () => {
    expect(reachesAgent("a", { enabled: false, scope: null })).toBe(false);
    expect(reachesAgent("a", { enabled: true, scope: null })).toBe(true);
    expect(reachesAgent("a", { enabled: true, scope: { agents: null } })).toBe(true);
    expect(reachesAgent("a", { enabled: true, scope: { agents: ["a"] } })).toBe(true);
    expect(reachesAgent("a", { enabled: true, scope: { agents: ["b"] } })).toBe(false);
  });
});

describe("counts", () => {
  test("an unread list counts nothing rather than zero", () => {
    expect(skillCounts(3, undefined)).toBeUndefined();
    expect(mcpCounts(2, undefined)).toBeUndefined();
    expect(pluginCounts(undefined)).toBeUndefined();
    expect(hookCounts(undefined)).toBeUndefined();
  });

  test("skills: delivered by Coffer and the agent's own folders", () => {
    expect(skillCounts(12, [{} as never, {} as never])).toEqual({ coffer: 12, own: 2 });
  });

  test("MCP: the coffer entry is the gateway, not one of the agent's own", () => {
    const entry = (name: string, extra: Partial<McpEntryOut> = {}) =>
      ({ name, is_coffer: false, matches_resource: null, ...extra }) as McpEntryOut;
    expect(
      mcpCounts(5, [
        entry("coffer", { is_coffer: true }),
        entry("github", { matches_resource: "github" }),
        entry("linear"),
      ]),
    ).toEqual({ coffer: 5, own: 2, duplicates: 1 });
  });

  test("plugins and hooks", () => {
    const p = (enabled: boolean, marketplace: string) => ({ enabled, marketplace }) as PluginOut;
    expect(pluginCounts([p(true, "a"), p(false, "a"), p(true, "b")])).toEqual({
      total: 3,
      enabled: 2,
      marketplaces: 2,
    });
    const hooks = {
      items: [
        { coffer: true, path: "/s.json" },
        { coffer: false, path: "/s.json" },
        { coffer: false, path: "/l.json" },
      ],
    } as AgentHooksOut;
    expect(hookCounts(hooks)).toEqual({ total: 3, coffer: 1, files: 2, cofferState: null });
  });

  test("Coffer's memory hook on four events is one hook", () => {
    const coffer = (event: string) => ({ coffer: true, path: "/s.json", event });
    const hooks = {
      items: [
        coffer("SessionStart"),
        coffer("UserPromptSubmit"),
        coffer("PreToolUse"),
        coffer("PostToolUse"),
        { coffer: false, path: "/s.json", event: "Stop" },
      ],
      coffer_hook: { health: "current", trust: "untrusted" },
    } as unknown as AgentHooksOut;
    expect(hookCounts(hooks)).toEqual({ total: 2, coffer: 1, files: 1, cofferState: "untrusted" });
    const missing = {
      items: [{ coffer: false, path: "/h.json", event: "PreToolUse" }],
      coffer_hook: { health: "missing", trust: "not_required" },
    } as unknown as AgentHooksOut;
    expect(hookCounts(missing)?.cofferState).toBe("missing");
  });
});

describe("owner filter", () => {
  const rows = [{ owner: "coffer" as const }, { owner: "own" as const }, { owner: "own" as const }];
  test("parses, filters and counts by owner", () => {
    expect(parseOwnerFilter("own")).toBe("own");
    expect(parseOwnerFilter("nonsense")).toBe("all");
    expect(parseOwnerFilter(null)).toBe("all");
    expect(filterByOwner(rows, "all")).toHaveLength(3);
    expect(filterByOwner(rows, "own")).toHaveLength(2);
    expect(countByOwner(rows)).toEqual({ coffer: 1, own: 2 });
  });
});
