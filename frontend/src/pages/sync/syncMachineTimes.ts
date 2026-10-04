// frontend/src/pages/sync/syncMachineTimes.ts
//
// How the Machines tab and the Remote tab write a time, the way a person says
// it: "Now", "12 minutes ago", "3 hours ago", then "21 Aug · 39 days ago" —
// and a clock time ("14:32") or a short date ("21 Aug") for a round. Pure:
// the clock and the translator are passed in.
import type { TFunction } from "i18next";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** A machine not seen for this long is shown in the warning tone. */
const STALE_AFTER_MS = 7 * DAY;

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function clock(d: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

function shortDate(d: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(d);
}

/** "14:32" today, "21 Aug" before — when a round ran. */
export function roundTime(iso: string, now: Date, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return sameDay(d, now) ? clock(d, locale) : shortDate(d, locale);
}

/** "Today 14:20" / "21 Aug 14:20" — a round named in a confirmation. */
export function roundMoment(iso: string, now: Date, t: TFunction, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return sameDay(d, now)
    ? t("sync.machines.time.today", { time: clock(d, locale) })
    : `${shortDate(d, locale)} ${clock(d, locale)}`;
}

/** When a machine was last seen, relative to `now`; null reads "Never". */
export function lastSeenLabel(iso: string | null, now: Date, t: TFunction, locale: string): string {
  if (!iso) return t("sync.machines.never");
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const ago = now.getTime() - d.getTime();
  if (ago < 2 * MINUTE) return t("sync.machines.time.now");
  if (ago < HOUR) return t("sync.machines.time.minutesAgo", { count: Math.floor(ago / MINUTE) });
  if (ago < DAY) return t("sync.machines.time.hoursAgo", { count: Math.floor(ago / HOUR) });
  return t("sync.machines.time.daysAgo", {
    date: shortDate(d, locale),
    count: Math.floor(ago / DAY),
  });
}

/** Whether a machine has not been seen for a week or more. */
export function isStale(iso: string | null, now: Date): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return !Number.isNaN(d.getTime()) && now.getTime() - d.getTime() >= STALE_AFTER_MS;
}
