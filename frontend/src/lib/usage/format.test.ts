// src/lib/usage/format.test.ts — the Usage page's number, money and day formats in en and zh.
import { describe, expect, test } from "vitest";

import {
  allUnpriced,
  formatCost,
  formatCount,
  formatDay,
  formatTokens,
  niceTicks,
  splitDuration,
} from "./format";

describe("formatTokens", () => {
  test("compacts to three significant digits from a thousand up", () => {
    expect(formatTokens(6_000_000, "en")).toBe("6.00M");
    expect(formatTokens(696_000, "en")).toBe("696K");
    expect(formatTokens(27_040_000, "en")).toBe("27.0M");
    expect(formatTokens(1_060_000, "en")).toBe("1.06M");
  });
  test("small counts stay exact", () => {
    expect(formatTokens(0, "en")).toBe("0");
    expect(formatTokens(842, "en")).toBe("842");
  });
  test("zh uses its own compact units", () => {
    expect(formatTokens(6_000_000, "zh")).toBe("600万");
  });
});

describe("formatCount and formatCost", () => {
  test("groups thousands", () => {
    expect(formatCount(3092, "en")).toBe("3,092");
  });
  test("money is dollars to the cent in both languages", () => {
    expect(formatCost(25.81, "en")).toBe("$25.81");
    expect(formatCost(0, "en")).toBe("$0.00");
    expect(formatCost(25.81, "zh")).toBe("$25.81");
  });
  test("a cost under a cent is not rounded to zero", () => {
    expect(formatCost(0.004, "en")).toBe("<$0.01");
  });
  test("axis ticks can drop the cents", () => {
    expect(formatCost(4, "en", 0)).toBe("$4");
  });
});

describe("dates and times", () => {
  const at = new Date(2026, 8, 23, 14, 2);
  test("days read day-first in English", () => {
    expect(formatDay(at, "en", "short")).toBe("Wed 23");
    expect(formatDay(at, "en", "long")).toBe("Wed 23 Sep");
    expect(formatDay(at, "en", "date")).toBe("23 Sep 2026");
  });
  test("durations split into days, hours and minutes", () => {
    expect(splitDuration((2 * 60 + 24) * 60_000)).toEqual({ days: 0, hours: 2, minutes: 24 });
    expect(splitDuration(((5 * 24 + 18) * 60 + 3) * 60_000)).toEqual({
      days: 5,
      hours: 18,
      minutes: 3,
    });
    expect(splitDuration(-5)).toEqual({ days: 0, hours: 0, minutes: 0 });
  });
});

describe("niceTicks", () => {
  test("covers the maximum in at most four round steps", () => {
    expect(niceTicks(6.03)).toEqual({ step: 2, ticks: [0, 2, 4, 6, 8] });
    expect(niceTicks(5.37)).toEqual({ step: 2, ticks: [0, 2, 4, 6] });
    expect(niceTicks(0.3).ticks).toEqual([0, 0.1, 0.2, 0.3]);
  });
  test("an empty chart still has an axis", () => {
    expect(niceTicks(0)).toEqual({ step: 1, ticks: [0, 1] });
  });
});

describe("allUnpriced", () => {
  test("only a range with requests, every one unpriced, has no cost", () => {
    expect(allUnpriced({ requests: 3, unpriced_requests: 3 })).toBe(true);
    expect(allUnpriced({ requests: 3, unpriced_requests: 1 })).toBe(false);
    expect(allUnpriced({ requests: 0, unpriced_requests: 0 })).toBe(false);
  });
});
