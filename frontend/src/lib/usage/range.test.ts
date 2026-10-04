// src/lib/usage/range.test.ts — the Usage range and grouping round-trip through the URL; local-day arithmetic.
import { describe, expect, test } from "vitest";

import { daysBetween, localDay, rangeOf, readUsageQuery, writeUsageQuery } from "./range";

const sp = (s: string) => new URLSearchParams(s);

describe("readUsageQuery", () => {
  test("reads the provider grouping", () => {
    expect(readUsageQuery(sp("by=provider"))).toEqual({ range: "7d", group_by: "provider" });
  });

  test("defaults to the last 7 days by model", () => {
    expect(readUsageQuery(sp(""))).toEqual({ range: "7d", group_by: "model" });
  });
  test("reads a preset and a grouping", () => {
    expect(readUsageQuery(sp("range=30d&by=agent"))).toEqual({ range: "30d", group_by: "agent" });
  });
  test("reads a custom range of two days", () => {
    expect(readUsageQuery(sp("range=2026-09-01..2026-09-29"))).toEqual({
      range: "custom",
      from: "2026-09-01",
      to: "2026-09-29",
      group_by: "model",
    });
  });
  test("a custom range open to now runs to today", () => {
    expect(rangeOf("2026-09-01..now", new Date(2026, 8, 20))).toEqual({
      range: "custom",
      from: "2026-09-01",
      to: "2026-09-20",
    });
  });
  test("a malformed or reversed custom range falls back to the default", () => {
    expect(readUsageQuery(sp("range=2026-09-29..2026-09-01")).range).toBe("7d");
    expect(readUsageQuery(sp("range=yesterday")).range).toBe("7d");
    expect(readUsageQuery(sp("range=24h&by=cost"))).toEqual({ range: "7d", group_by: "model" });
  });
});

describe("writeUsageQuery", () => {
  test("never spells out the defaults and keeps unrelated params", () => {
    expect(
      writeUsageQuery(sp("x=1&range=30d"), { range: "7d", group_by: "model" }).toString(),
    ).toBe("x=1");
  });
  test("round-trips a custom range", () => {
    const q = { range: "custom", from: "2026-09-01", to: "2026-09-03", group_by: "day" } as const;
    const out = writeUsageQuery(sp("tab=usage"), q);
    expect(out.toString()).toBe("tab=usage&range=2026-09-01..2026-09-03&by=day");
    expect(readUsageQuery(out)).toEqual(q);
  });
});

describe("local days", () => {
  test("lists every day of a range, both ends included, across a month end", () => {
    expect(daysBetween("2026-08-30", "2026-09-02")).toEqual([
      "2026-08-30",
      "2026-08-31",
      "2026-09-01",
      "2026-09-02",
    ]);
    expect(daysBetween("2026-09-02", "2026-09-01")).toEqual([]);
  });
  test("localDay pads month and day", () => {
    expect(localDay(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("usage filters in the URL", () => {
  test("reads and writes the agent and provider filters", () => {
    const q = readUsageQuery(sp("agent=codex&provider=conn-1"));
    expect(q).toEqual({
      range: "7d",
      group_by: "model",
      agent_type: "codex",
      connection_uid: "conn-1",
    });
    expect(writeUsageQuery(sp("tab=usage"), q).toString()).toBe(
      "tab=usage&agent=codex&provider=conn-1",
    );
    expect(writeUsageQuery(sp("agent=codex"), { range: "7d", group_by: "model" }).toString()).toBe(
      "",
    );
  });
});
