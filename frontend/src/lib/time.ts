// src/lib/time.ts — dates and times as the Shell canvas prints them.
//
// One home for the three shapes Settings uses: a day with its year ("30 Sep
// 2026" — a release, a price list), a clock time ("14:02"), and a moment that
// reads "today at 12:00" for today and "30 Sep at 12:00" for any other day.
// English prints the day first and the month short; Chinese prints 9月30日.
import type { TFunction } from "i18next";

const zh = (lang: string) => lang.startsWith("zh");

/** "30 Sep" / "30 Sep 2026" in English (day first, three-letter month), "9月30日" / "2026年9月30日" in Chinese. */
function dayText(date: Date, lang: string, withYear: boolean): string {
  if (zh(lang)) {
    const md = `${date.getMonth() + 1}月${date.getDate()}日`;
    return withYear ? `${date.getFullYear()}年${md}` : md;
  }
  const month = date.toLocaleDateString("en-US", { month: "short" });
  return `${date.getDate()} ${month}${withYear ? ` ${date.getFullYear()}` : ""}`;
}

/** A Date -> "30 Sep 2026" ("2026年9月30日" in Chinese). */
export function formatDay(date: Date, lang: string): string {
  return dayText(date, lang, true);
}

/** A Date -> "14:02", 24-hour, local time. */
export function formatClock(date: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(date.getHours())}:${p(date.getMinutes())}`;
}

function isToday(date: Date, now: Date): boolean {
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

/** "today at 12:00", or "30 Sep at 12:00" for another day; the raw text when `iso` is not a date. */
export function formatMoment(iso: string, lang: string, t: TFunction, now = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const time = formatClock(date);
  if (isToday(date, now)) return t("common.time.todayAt", { time });
  const day = dayText(date, lang, false);
  return t("common.time.dayAt", { day, time });
}

/** "14:02" for today; "30 Sep at 14:02" for another day. */
export function formatClockOrMoment(
  date: Date,
  lang: string,
  t: TFunction,
  now = new Date(),
): string {
  return isToday(date, now) ? formatClock(date) : formatMoment(date.toISOString(), lang, t, now);
}

// --- relative time (Foundations 0.3.03) ---------------------------------------
// "just now" · "12 min ago" · "3 h ago" · "Yesterday" · then the date as the US
// writes it ("Sep 29", with the year once it is a past year). Chinese keeps the
// same steps (刚刚 · 12 分钟前 · 3 小时前 · 昨天 · 9月29日). Every relative time
// carries its exact local time on hover (`formatExact`).

/** "Sep 29" / "Sep 29, 2025" in English, "9月29日" / "2025年9月29日" in Chinese. */
export function formatUsDay(date: Date, lang: string, withYear: boolean): string {
  if (zh(lang)) return dayText(date, lang, withYear);
  const month = date.toLocaleDateString("en-US", { month: "short" });
  return `${month} ${date.getDate()}${withYear ? `, ${date.getFullYear()}` : ""}`;
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** How long ago `iso` was, in the steps above; the raw text when `iso` is not a date. */
export function formatRelative(
  iso: string | Date,
  lang: string,
  t: TFunction,
  now = new Date(),
): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return String(iso);
  const minutes = Math.floor((now.getTime() - date.getTime()) / 60_000);
  if (minutes < 1) return t("common.time.justNow");
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days === 0) {
    return minutes < 60
      ? t("common.time.minAgo", { count: minutes })
      : t("common.time.hAgo", { count: Math.floor(minutes / 60) });
  }
  if (days === 1) return t("common.time.yesterday");
  return formatUsDay(date, lang, date.getFullYear() !== now.getFullYear());
}

/** "Oct 3, 2026 at 09:41:07" ("2026年10月3日 09:41:07"): the exact local time, to the second. */
export function formatExact(iso: string | Date, lang: string): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(date.getTime())) return String(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  const clock = `${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}`;
  if (zh(lang)) return `${formatDay(date, lang)} ${clock}`;
  return `${formatUsDay(date, lang, true)} at ${clock}`;
}
