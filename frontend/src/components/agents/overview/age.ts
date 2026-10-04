// src/components/agents/overview/age.ts — how long ago something happened, as the Overview's short "2h".
//
// The board prints ages, not timestamps, for recent sessions and the memory
// hook's last fire. One unit only, rounded down: minutes under an hour, hours
// under a day, days under two weeks, weeks after that.
import type { TFunction } from "i18next";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

type AgeUnit = "now" | "m" | "h" | "d" | "w";

function ageOf(iso: string, now: number): { unit: AgeUnit; count: number } | null {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const ms = Math.max(0, now - then);
  if (ms < MINUTE) return { unit: "now", count: 0 };
  if (ms < HOUR) return { unit: "m", count: Math.floor(ms / MINUTE) };
  if (ms < DAY) return { unit: "h", count: Math.floor(ms / HOUR) };
  if (ms < 2 * WEEK) return { unit: "d", count: Math.floor(ms / DAY) };
  return { unit: "w", count: Math.floor(ms / WEEK) };
}

/** "2h ago"-style age of `iso` ("5h" in en, "5 小时前" in zh); `null` for an unreadable time. */
export function formatAgo(t: TFunction, iso: string, now = Date.now()): string | null {
  const age = ageOf(iso, now);
  if (age === null) return null;
  if (age.unit === "now") return t("agents.overviewTab.age.now");
  return t("agents.overviewTab.age.ago", {
    age: t(`agents.overviewTab.age.${age.unit}`, { count: age.count }),
  });
}
