// src/components/palette/paletteItems.test.ts — the palette's match and ranking rule.
import { describe, expect, test } from "vitest";

import {
  filterItems,
  matchRank,
  objectItem,
  objectPath,
  searchGroups,
  type PaletteItem,
} from "./paletteItems";

function page(label: string, to: string): PaletteItem {
  return { id: to, kind: "page", label, haystack: [label], target: { type: "route", to } };
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
    const item = objectItem("mcpServer", { uid: "u1", name: "gh-server", title: "GitHub" });
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
    const item = objectItem("skill", { uid: "u1", name: "pdf tools", title: "PDF tools" });
    expect(item.label).toBe("PDF tools");
    expect(item.detail).toBe("pdf tools");
    expect(item.target).toEqual({ type: "route", to: "/skills/pdf%20tools" });
  });

  test("an object without a title shows its name alone", () => {
    const item = objectItem("agent", { uid: "a1", name: "claude", title: "  " });
    expect(item.label).toBe("claude");
    expect(item.detail).toBeUndefined();
    expect(item.haystack).toEqual(["claude"]);
  });

  test("every kind has a detail route: an agent by type, by name where it is fixed, by uid where it is not", () => {
    const o = (uid: string) => ({ uid, name: `${uid}-name` });
    expect(objectPath("mcpServer", o("m1"))).toBe("/mcp-servers/m1-name");
    // Custom tool groups are palette objects too, addressed by the group name.
    expect(objectPath("customTool", o("g1"))).toBe("/custom-tools/g1-name");
    expect(objectPath("skill", o("s1"))).toBe("/skills/s1-name");
    expect(objectPath("provider", o("p"))).toBe("/model-providers/p");
    expect(objectPath("knowledge", o("k"))).toBe("/knowledge/k");
    expect(objectPath("memory", o("m"))).toBe("/memory/m");
    expect(objectPath("channel", o("c"))).toBe("/channels/c");
    expect(objectPath("agent", o("a"))).toBe("/agents/a");
    expect(objectPath("agent", { ...o("a"), type: "claude_code" })).toBe("/agents/claude_code");
  });

  test("a CLI opens its page by its command, and is found by its title too", () => {
    const item = objectItem("cli", { uid: "gh", name: "gh", title: "GitHub CLI" });
    expect(item.target).toEqual({ type: "route", to: "/clis/gh" });
    expect(item.haystack).toEqual(["GitHub CLI", "gh"]);
  });
});

describe("searchGroups", () => {
  test("the best hit leads, then Pages, then one group per kind in sidebar order", () => {
    const pages = [page("Skills", "/skills"), page("Secrets", "/secrets")];
    const objects = [
      objectItem("skill", { uid: "s1", name: "sentry-triage" }),
      objectItem("mcpServer", { uid: "m1", name: "sentry" }),
    ];
    const groups = searchGroups(pages, objects, "s");
    expect(groups.map((g) => g.key)).toEqual(["best", "pages", "mcpServer", "skill"]);
    expect(groups[0].items.map((i) => i.id)).toEqual(["/skills"]);
    expect(groups[1].items.map((i) => i.id)).toEqual(["/secrets"]);
  });

  test("an exact name wins Best match over an earlier prefix hit", () => {
    const objects = [
      objectItem("skill", { uid: "s1", name: "sentry-triage" }),
      objectItem("mcpServer", { uid: "m1", name: "sentry" }),
    ];
    expect(searchGroups([], objects, "sentry")[0].items[0].id).toBe("mcpServer-m1");
  });

  test("nothing matching leaves no groups", () => {
    expect(searchGroups([page("Usage", "/usage")], [], "zzz")).toEqual([]);
  });

  test("a secret opens the Secrets page, which has no detail route", () => {
    expect(objectPath("secret", { uid: "API_KEY", name: "API_KEY" })).toBe("/secrets");
  });
});
