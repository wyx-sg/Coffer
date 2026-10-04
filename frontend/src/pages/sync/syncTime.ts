// frontend/src/pages/sync/syncTime.ts
//
// How the Sync page writes time and the remote: "Today 14:20", "Yesterday
// 22:20", "14:32:01", "12 minutes ago", "every hour", and the host a remote
// URL points at. Pure: the clock and the translator are passed in, so a test
// pins "now" instead of racing it.
import type { TFunction } from "i18next";

import { formatDateTime } from "@/lib/utils";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** "HH:mm" in local time. */
export function clock(iso: string): string {
  return formatDateTime(iso).slice(11, 16);
}

/** "HH:mm:ss" in local time — a snapshot or a step, where seconds matter. */
export function clockSeconds(iso: string): string {
  return formatDateTime(iso).slice(11, 19);
}

/** The day a moment falls on, as the Rounds table heads it: Today, Yesterday, or the date. */
export function dayLabel(iso: string, t: TFunction, now: Date = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  if (sameDay(at, now)) return t("sync.rounds.today");
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(at, yesterday)) return t("sync.rounds.yesterday");
  return formatDateTime(iso).slice(0, 10);
}

/** "Today 14:20". */
export function dayTime(iso: string, t: TFunction, now: Date = new Date()): string {
  return `${dayLabel(iso, t, now)} ${clock(iso)}`;
}

/** "Today 08:20 – 13:20", or both days when the stretch crosses midnight. */
export function daySpan(from: string, to: string, t: TFunction, now: Date = new Date()): string {
  const a = dayLabel(from, t, now);
  const b = dayLabel(to, t, now);
  return a === b ? `${a} ${clock(from)} – ${clock(to)}` : `${a} ${clock(from)} – ${b} ${clock(to)}`;
}

/** "just now", "12 minutes ago", "3 hours ago", else null (the time says enough). */
export function agoPhrase(iso: string, t: TFunction, now: Date = new Date()): string | null {
  const ago = now.getTime() - new Date(iso).getTime();
  if (!Number.isFinite(ago) || ago < 0) return null;
  if (ago < MINUTE) return t("sync.banner.justNow");
  if (ago < HOUR) return t("sync.banner.minutesAgo", { count: Math.floor(ago / MINUTE) });
  if (ago < 24 * HOUR) return t("sync.banner.hoursAgo", { count: Math.floor(ago / HOUR) });
  return null;
}

/** How often a round runs: "every hour", "every 5 minutes", "every 2 hours". */
export function intervalPhrase(seconds: number, t: TFunction): string {
  if (seconds > 0 && seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return hours === 1 ? t("sync.header.everyHour") : t("sync.header.everyHours", { count: hours });
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  return t("sync.header.everyMinutes", { count: minutes });
}

/** The host a remote URL names: `git@github.com:me/v.git` and `https://github.com/me/v` both → github.com. */
export function remoteHost(url: string): string {
  const scp = /^[^@/\s]+@([^:/\s]+):/.exec(url);
  if (scp) return scp[1];
  try {
    return new URL(url).hostname || url;
  } catch {
    return url;
  }
}
