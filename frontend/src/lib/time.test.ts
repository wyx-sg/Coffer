import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import {
  formatClock,
  formatClockOrMoment,
  formatDay,
  formatDayShort,
  formatExact,
  formatMoment,
  formatRelative,
} from "./time";

// The English templates, as the locale ships them.
const t = ((key: string, o: Record<string, string>) =>
  key === "common.time.todayAt" ? `today at ${o.time}` : `${o.day} at ${o.time}`) as TFunction;
const NOW = new Date(2026, 9, 3, 15, 0);

describe("time formats", () => {
  test("a day prints day, short month, year", () => {
    expect(formatDay(new Date(2026, 8, 30), "en")).toBe("30 Sep 2026");
    expect(formatDay(new Date(2026, 8, 30), "zh")).toBe("2026年9月30日");
  });

  test("a short day leaves the year out", () => {
    expect(formatDayShort(new Date(2026, 8, 27), "en")).toBe("27 Sep");
    expect(formatDayShort(new Date(2026, 8, 27), "zh")).toBe("9月27日");
  });

  test("a clock time is 24-hour", () => {
    expect(formatClock(new Date(2026, 9, 3, 9, 5))).toBe("09:05");
  });

  test("a moment says today, or the day", () => {
    expect(formatMoment(new Date(2026, 9, 3, 12, 0).toISOString(), "en", t, NOW)).toBe(
      "today at 12:00",
    );
    expect(formatMoment(new Date(2026, 8, 30, 12, 0).toISOString(), "en", t, NOW)).toBe(
      "30 Sep at 12:00",
    );
    expect(formatMoment("nope", "en", t, NOW)).toBe("nope");
  });

  test("a check time is the clock today and the moment otherwise", () => {
    expect(formatClockOrMoment(new Date(2026, 9, 3, 14, 2), "en", t, NOW)).toBe("14:02");
    expect(formatClockOrMoment(new Date(2026, 8, 30, 14, 2), "en", t, NOW)).toBe("30 Sep at 14:02");
  });
});

describe("relative time", () => {
  const rt = ((key: string, o?: { count: number }) =>
    ({
      "common.time.justNow": "just now",
      "common.time.minAgo": `${o?.count} min ago`,
      "common.time.hAgo": `${o?.count} h ago`,
      "common.time.yesterday": "Yesterday",
    })[key]) as TFunction;
  const at = (d: Date) => formatRelative(d, "en", rt, NOW);

  test("steps from just now to minutes to hours to yesterday to a date", () => {
    expect(at(new Date(2026, 9, 3, 14, 59, 40))).toBe("just now");
    expect(at(new Date(2026, 9, 3, 14, 48))).toBe("12 min ago");
    expect(at(new Date(2026, 9, 3, 12, 0))).toBe("3 h ago");
    expect(at(new Date(2026, 9, 2, 23, 0))).toBe("Yesterday");
    expect(at(new Date(2026, 8, 29, 10, 0))).toBe("Sep 29");
    expect(at(new Date(2025, 6, 3, 10, 0))).toBe("Jul 3, 2025");
  });

  test("Chinese dates and the exact time", () => {
    expect(formatRelative(new Date(2026, 8, 29), "zh", rt, NOW)).toBe("9月29日");
    expect(formatExact(new Date(2026, 9, 3, 9, 41, 7), "en")).toBe("Oct 3, 2026 at 09:41:07");
    expect(formatExact(new Date(2026, 9, 3, 9, 41, 7), "zh")).toBe("2026年10月3日 09:41:07");
  });

  test("a time that is not a date is printed as given", () => {
    expect(formatRelative("nope", "en", rt, NOW)).toBe("nope");
  });
});
