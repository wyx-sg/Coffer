import { describe, expect, test } from "vitest";
import { elapsedMs, formatDuration, formatToolDuration } from "./duration";

describe("formatDuration", () => {
  test("whole seconds under a minute", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(42_400)).toBe("42s");
    expect(formatDuration(59_400)).toBe("59s");
  });
  test("minutes and zero-padded seconds from a minute on", () => {
    expect(formatDuration(60_000)).toBe("1m 00s");
    expect(formatDuration(68_000)).toBe("1m 08s");
    expect(formatDuration(3_725_000)).toBe("62m 05s");
  });
  test("a negative span counts as zero", () => {
    expect(formatDuration(-5)).toBe("0s");
  });
});

describe("formatToolDuration", () => {
  test("tenths of a second under ten seconds", () => {
    expect(formatToolDuration(300)).toBe("0.3s");
    expect(formatToolDuration(6_100)).toBe("6.1s");
  });
  test("a long call is worded like a turn", () => {
    expect(formatToolDuration(12_000)).toBe("12s");
    expect(formatToolDuration(75_000)).toBe("1m 15s");
  });
});

describe("elapsedMs", () => {
  test("is the span between two timestamps", () => {
    expect(elapsedMs("2026-10-03T10:14:00Z", "2026-10-03T10:14:42Z")).toBe(42_000);
  });
  test("is null when an end is missing or unreadable", () => {
    expect(elapsedMs("2026-10-03T10:14:00Z", null)).toBeNull();
    expect(elapsedMs("nope", "2026-10-03T10:14:42Z")).toBeNull();
  });
});
