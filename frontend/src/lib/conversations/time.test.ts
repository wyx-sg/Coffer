import { describe, expect, test } from "vitest";

import { clock, groupByTime, timeBucket } from "./time";

// Local-time dates throughout: the edges are the viewer's midnight.
const NOW = new Date(2026, 5, 15, 12, 0, 0); // Mon 15 Jun 2026, noon
const at = (y: number, m: number, d: number, h = 12, min = 0) =>
  new Date(y, m, d, h, min).toISOString();

describe("timeBucket", () => {
  test("local midnight splits today from yesterday", () => {
    expect(timeBucket(at(2026, 5, 15, 0, 0), NOW)).toBe("today");
    expect(timeBucket(at(2026, 5, 14, 23, 59), NOW)).toBe("yesterday");
    expect(timeBucket(at(2026, 5, 14, 0, 0), NOW)).toBe("yesterday");
    expect(timeBucket(at(2026, 5, 13, 23, 59), NOW)).toBe("week");
  });

  test("the 7- and 30-day edges", () => {
    expect(timeBucket(at(2026, 5, 8, 0, 0), NOW)).toBe("week"); // 7 days back
    expect(timeBucket(at(2026, 5, 7, 23, 59), NOW)).toBe("month"); // 8 days back
    expect(timeBucket(at(2026, 4, 16, 0, 0), NOW)).toBe("month"); // 30 days back
    expect(timeBucket(at(2026, 4, 15, 23, 59), NOW)).toBe("earlier"); // 31 days back
  });

  test("just after midnight, yesterday evening is still yesterday", () => {
    const early = new Date(2026, 5, 15, 0, 5);
    expect(timeBucket(at(2026, 5, 14, 23, 50), early)).toBe("yesterday");
    expect(timeBucket(at(2026, 5, 15, 0, 1), early)).toBe("today");
  });

  test("a future or unreadable timestamp does not break the list", () => {
    expect(timeBucket(at(2026, 5, 16, 9), NOW)).toBe("today");
    expect(timeBucket("not a date", NOW)).toBe("earlier");
  });
});

describe("groupByTime", () => {
  const rows = [
    { id: "old", t: at(2026, 0, 2) },
    { id: "y", t: at(2026, 5, 14, 9) },
    { id: "t1", t: at(2026, 5, 15, 8) },
    { id: "t2", t: at(2026, 5, 15, 11) },
    { id: "w", t: at(2026, 5, 10) },
  ];

  test("groups newest first, rows newest first, empty groups left out", () => {
    const groups = groupByTime(rows, (r) => r.t, NOW);
    expect(groups.map((g) => g.bucket)).toEqual(["today", "yesterday", "week", "earlier"]);
    expect(groups[0].items.map((r) => r.id)).toEqual(["t2", "t1"]);
  });

  test("nothing in, nothing out", () => {
    expect(groupByTime([], () => "", NOW)).toEqual([]);
  });
});

test("clock is HH:MM", () => {
  expect(clock(at(2026, 5, 15, 7, 5))).toBe("07:05");
});
