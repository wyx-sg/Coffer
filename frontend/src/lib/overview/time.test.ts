// src/lib/overview/time.test.ts — "Since 09:12", "Since yesterday" or a date.
import { expect, test } from "vitest";

import { describeSince, formatShortTime } from "./time";

const now = new Date(2026, 8, 30, 14, 6);
const local = (d: number, h: number, m: number) => new Date(2026, 8, d, h, m).toISOString();

test("today reads as its time, yesterday as yesterday, older as its date", () => {
  expect(describeSince(local(30, 9, 12), now)).toEqual({ kind: "today", time: "09:12" });
  expect(describeSince(local(29, 23, 0), now)).toEqual({ kind: "yesterday" });
  expect(describeSince(local(12, 8, 0), now)).toEqual({ kind: "date", date: "2026-09-12" });
});

test("no since, or a malformed one, has no label", () => {
  expect(describeSince(null, now)).toBeNull();
  expect(describeSince("not a date", now)).toBeNull();
});

test("a row's time drops the date only for today", () => {
  expect(formatShortTime(local(30, 14, 2), now)).toBe("14:02");
  expect(formatShortTime(local(28, 7, 5), now)).toBe("2026-09-28 07:05");
});
