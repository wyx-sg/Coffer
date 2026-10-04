// src/lib/conversations/filters.test.ts
import { describe, expect, it } from "vitest";

import { clearFilters, filtersSearch, hasLegacyChannel, isFiltered, parseFilters } from "./filters";

describe("conversation filters", () => {
  it("reads sources, agents, the search and the archived view from the URL", () => {
    expect(
      parseFilters(new URLSearchParams("source=coffer,ch2&agent=codex&archived=1&q=sentry")),
    ).toEqual({ source: ["coffer", "ch2"], agent: ["codex"], archived: true, q: "sentry" });
    expect(parseFilters(new URLSearchParams(""))).toEqual({
      source: [],
      agent: [],
      archived: false,
      q: "",
    });
  });

  it("round-trips through the URL, writing only what narrows the list", () => {
    expect(filtersSearch(parseFilters(new URLSearchParams("")))).toBe("");
    const f = { source: ["coffer", "ch1"], agent: ["codex"], archived: true, q: "a b" };
    expect(filtersSearch(f)).toBe("?source=coffer,ch1&agent=codex&archived=1&q=a+b");
    expect(parseFilters(new URLSearchParams(filtersSearch(f)))).toEqual(f);
  });

  it("reads a legacy ?channel=<uid> as one source", () => {
    const params = new URLSearchParams("channel=ch1&agent=codex");
    expect(hasLegacyChannel(params)).toBe(true);
    const f = parseFilters(params);
    expect(f.source).toEqual(["ch1"]);
    // Written back, the legacy key is gone.
    expect(filtersSearch(f)).toBe("?source=ch1&agent=codex");
    expect(hasLegacyChannel(new URLSearchParams(filtersSearch(f)))).toBe(false);
    expect(parseFilters(new URLSearchParams("source=ch1&channel=ch1")).source).toEqual(["ch1"]);
  });

  it("counts a source, an agent or a search as narrowing, and clears them but not the archived view", () => {
    const base = parseFilters(new URLSearchParams("archived=1"));
    expect(isFiltered(base)).toBe(false);
    expect(isFiltered({ ...base, q: "  " })).toBe(false);
    const narrowed = { ...base, source: ["ch1"], agent: ["codex"], q: "x" };
    expect(isFiltered(narrowed)).toBe(true);
    expect(clearFilters(narrowed)).toEqual(base);
  });
});
