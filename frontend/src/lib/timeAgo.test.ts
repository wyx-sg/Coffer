// src/lib/timeAgo.test.ts — how long ago a time was.
import { describe, expect, test } from "vitest";

import { timeAgo } from "./timeAgo";

describe("timeAgo", () => {
  const now = Date.parse("2026-09-30T12:00:00Z");
  test("picks the largest whole unit", () => {
    expect(timeAgo("2026-09-30T10:00:00Z", "en", now)).toBe("2 hours ago");
    expect(timeAgo("2026-09-30T11:46:00Z", "en", now)).toBe("14 minutes ago");
    expect(timeAgo("2026-09-29T12:00:00Z", "en", now)).toBe("yesterday");
    expect(timeAgo("2026-09-30T11:59:50Z", "en", now)).toBe("this minute");
  });
});
