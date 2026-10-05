// src/lib/conversations/filters.test.ts
import { describe, expect, it } from "vitest";

import { clearFilters, filtersSearch, isFiltered, parseFilters } from "./filters";

describe("conversation filters", () => {
  it("reads sources, agents and the search from the URL", () => {
    expect(parseFilters(new URLSearchParams("source=ch1,ch2&agent=codex&q=sentry"))).toEqual({
      source: ["ch1", "ch2"],
      agent: ["codex"],
      q: "sentry",
    });
    expect(parseFilters(new URLSearchParams(""))).toEqual({ source: [], agent: [], q: "" });
  });

  it("round-trips through the URL, writing only what narrows the list", () => {
    expect(filtersSearch(parseFilters(new URLSearchParams("")))).toBe("");
    const f = { source: ["ch2", "ch1"], agent: ["codex"], q: "a b" };
    expect(filtersSearch(f)).toBe("?source=ch2,ch1&agent=codex&q=a+b");
    expect(parseFilters(new URLSearchParams(filtersSearch(f)))).toEqual(f);
  });

  it("reads `local` as a source beside channel uids", () => {
    const f = parseFilters(new URLSearchParams("source=local,ch1"));
    expect(f.source).toEqual(["local", "ch1"]);
    expect(filtersSearch(f)).toBe("?source=local,ch1");
  });

  it("counts a channel, an agent or a search as narrowing, and clears them all", () => {
    const base = parseFilters(new URLSearchParams(""));
    expect(isFiltered(base)).toBe(false);
    expect(isFiltered({ ...base, q: "  " })).toBe(false);
    const narrowed = { ...base, source: ["ch1"], agent: ["codex"], q: "x" };
    expect(isFiltered(narrowed)).toBe(true);
    expect(clearFilters()).toEqual(base);
  });
});
