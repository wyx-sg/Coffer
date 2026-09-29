// src/components/palette/paletteItems.test.ts — the palette's match and ranking rule.
import { describe, expect, test } from "vitest";

import { filterItems, matchRank, objectItem, objectPath, type PaletteItem } from "./paletteItems";

function page(label: string, to: string): PaletteItem {
  return { id: to, group: "pages", label, haystack: [label], target: { type: "route", to } };
}

describe("matchRank", () => {
  test("a prefix ranks above a substring, case-insensitively", () => {
    expect(matchRank(page("Activity", "/activity"), "ACT")).toBe(0);
    expect(matchRank(page("Contacts", "/c"), "act")).toBe(1);
    expect(matchRank(page("Usage", "/usage"), "act")).toBeNull();
  });

  test("an empty or blank query matches everything", () => {
    expect(matchRank(page("Usage", "/usage"), "")).toBe(0);
    expect(matchRank(page("Usage", "/usage"), "   ")).toBe(0);
  });

  test("any haystack text may carry the match", () => {
    const item = objectItem("mcpServer", { uid: "u1", name: "gh-server", title: "GitHub" }, "MCP");
    expect(matchRank(item, "git")).toBe(0);
    expect(matchRank(item, "server")).toBe(1);
  });
});

describe("filterItems", () => {
  test("keeps prefix matches first, then the given order", () => {
    const items = [page("Reactions", "/r"), page("Activity", "/a"), page("Actors", "/b")];
    expect(filterItems(items, "act").map((i) => i.id)).toEqual(["/a", "/b", "/r"]);
  });

  test("drops what does not match", () => {
    expect(filterItems([page("Usage", "/u")], "zzz")).toEqual([]);
  });
});

describe("objectItem", () => {
  test("shows the title with the name after it and opens a skill by its fixed name", () => {
    const item = objectItem("skill", { uid: "u1", name: "pdf tools", title: "PDF tools" }, "Skill");
    expect(item.label).toBe("PDF tools");
    expect(item.detail).toBe("pdf tools");
    expect(item.target).toEqual({ type: "route", to: "/skills/pdf%20tools" });
  });

  test("an object without a title shows its name alone", () => {
    const item = objectItem("agent", { uid: "a1", name: "claude", title: "  " }, "Agent");
    expect(item.label).toBe("claude");
    expect(item.detail).toBeUndefined();
    expect(item.haystack).toEqual(["claude"]);
  });

  test("every kind has a detail route: an agent by type, by name where it is fixed, by uid where it is not", () => {
    const o = (uid: string) => ({ uid, name: `${uid}-name` });
    expect(objectPath("mcpServer", o("m1"))).toBe("/mcp-servers/m1-name");
    expect(objectPath("skill", o("s1"))).toBe("/skills/s1-name");
    expect(objectPath("provider", o("p"))).toBe("/model-providers/p");
    expect(objectPath("knowledge", o("k"))).toBe("/knowledge/k");
    expect(objectPath("memory", o("m"))).toBe("/memory/m");
    expect(objectPath("channel", o("c"))).toBe("/channels/c");
    expect(objectPath("agent", o("a"))).toBe("/agents/a");
    expect(objectPath("agent", { ...o("a"), type: "claude_code" })).toBe("/agents/claude_code");
  });
});
