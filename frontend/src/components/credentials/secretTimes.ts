// src/components/credentials/secretTimes.ts — how the Secrets page writes when a secret was created and last used.
//
// Last used reads the way a person says it: "2 min ago", "1 hour ago",
// "14:32 today", "Yesterday", then a short date ("3 Jul"); a secret never
// used here reads "Never". Created is always the short date. Pure: the clock
// and the translator are passed in.
import type { TFunction } from "i18next";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

/** "12 Aug" in the UI's language; an unreadable timestamp is returned as given. */
export function shortDate(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(d);
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** When a secret was last used, relative to `now`. */
export function lastUsedLabel(
  iso: string | null | undefined,
  now: Date,
  t: TFunction,
  locale: string,
): string {
  if (!iso) return t("secrets.time.never");
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const ago = now.getTime() - d.getTime();
  if (ago < MINUTE) return t("secrets.time.justNow");
  if (ago < HOUR) return t("secrets.time.minutesAgo", { count: Math.floor(ago / MINUTE) });
  if (ago < 3 * HOUR) return t("secrets.time.hoursAgo", { count: Math.floor(ago / HOUR) });
  if (sameDay(d, now)) {
    const time = new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
    return t("secrets.time.today", { time });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(d, yesterday)) return t("secrets.time.yesterday");
  return shortDate(iso, locale);
}
