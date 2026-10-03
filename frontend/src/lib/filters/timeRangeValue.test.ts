import { describe, expect, it } from "vitest";

import {
  encodeCustom,
  formatCustom,
  isTime,
  normalizeRange,
  parseCustom,
  rangeParam,
  resolveRange,
} from "./timeRangeValue";

const NOW = new Date(2026, 9, 3, 12, 0, 0);

describe("timeRangeValue", () => {
  it("round-trips a custom range through its URL string", () => {
    const value = encodeCustom({ from: "2026-09-29T14:00", to: "now" });
    expect(value).toBe("2026-09-29T14:00..now");
    expect(parseCustom(value)).toEqual({ from: "2026-09-29T14:00", to: "now" });
  });

  it("rejects malformed custom ranges", () => {
    expect(parseCustom("24h")).toBeUndefined();
    expect(parseCustom("2026-02-31..now")).toBeUndefined();
    expect(parseCustom("2026-09-29T25:00..now")).toBeUndefined();
    expect(parseCustom("2026-09-29..junk")).toBeUndefined();
  });

  it("falls back for unknown values and keeps known ones", () => {
    const ids = ["1h", "24h"];
    expect(normalizeRange("1h", ids, "24h")).toBe("1h");
    expect(normalizeRange("bogus", ids, "24h")).toBe("24h");
    expect(normalizeRange(null, ids, "24h")).toBe("24h");
    expect(normalizeRange("2026-09-01..2026-09-20", ids, "24h")).toBe("2026-09-01..2026-09-20");
  });

  it("omits the default from the URL", () => {
    expect(rangeParam("24h", "24h")).toBeUndefined();
    expect(rangeParam("7d", "24h")).toBe("7d");
  });

  it("resolves rolling presets to a since bound", () => {
    expect(resolveRange("1h", NOW)).toEqual({ since: new Date(2026, 9, 3, 11).toISOString() });
    expect(resolveRange("nope", NOW)).toEqual({ since: undefined });
  });

  it("resolves today and this month to local midnight", () => {
    expect(resolveRange("today", NOW).since).toBe(new Date(2026, 9, 3).toISOString());
    expect(resolveRange("month", NOW).since).toBe(new Date(2026, 9, 1).toISOString());
  });

  it("resolves custom ranges, with whole days running to their end", () => {
    expect(resolveRange("2026-09-29T14:00..now", NOW)).toEqual({
      since: new Date(2026, 8, 29, 14).toISOString(),
    });
    expect(resolveRange("2026-09-01..2026-09-20", NOW)).toEqual({
      since: new Date(2026, 8, 1).toISOString(),
      until: new Date(2026, 8, 20, 23, 59, 59, 999).toISOString(),
    });
  });

  it("words a custom range for the pill", () => {
    expect(formatCustom({ from: "2026-09-29T14:00", to: "now" }, "en", "now", NOW)).toBe(
      "Sep 29, 14:00 – now",
    );
    expect(formatCustom({ from: "2026-09-01", to: "2026-09-20" }, "en", "now", NOW)).toBe(
      "Sep 1 – Sep 20",
    );
  });

  it("validates HH:MM", () => {
    expect(isTime("14:00")).toBe(true);
    expect(isTime("24:00")).toBe(false);
    expect(isTime("9:00")).toBe(false);
  });
});
