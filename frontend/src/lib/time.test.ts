import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";

import { formatClock, formatClockOrMoment, formatDay, formatMoment } from "./time";

// The English templates, as the locale ships them.
const t = ((key: string, o: Record<string, string>) =>
  key === "common.time.todayAt" ? `today at ${o.time}` : `${o.day} at ${o.time}`) as TFunction;
const NOW = new Date(2026, 9, 3, 15, 0);

describe("time formats", () => {
  test("a day prints day, short month, year", () => {
    expect(formatDay(new Date(2026, 8, 30), "en")).toBe("30 Sep 2026");
    expect(formatDay(new Date(2026, 8, 30), "zh")).toBe("2026年9月30日");
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
