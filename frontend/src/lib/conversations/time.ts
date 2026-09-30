// src/lib/conversations/time.ts
// How the Conversations list places a conversation in time: a day heading
// (Today / Yesterday / the date) over rows that each show the clock time of
// their last activity. Pure, and told "now", so it is unit-tested alone.
import type { TFunction } from "i18next";

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** The day heading a timestamp sits under. */
export function dayHeading(t: TFunction, iso: string, now: Date, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000);
  if (days === 0) return t("conversations.day.today");
  if (days === 1) return t("conversations.day.yesterday");
  return d.toLocaleDateString(locale, {
    day: "numeric",
    month: "short",
    year: d.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}

/** "HH:MM", locale-independent like every other timestamp in the app. */
export function clock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}
