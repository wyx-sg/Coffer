// src/lib/providers/priceDate.ts — the day a price list's data is from, as a reader reads it ("30 Sep 2026").
import { formatDay } from "@/lib/time";

/** `2026-09-30` in the reader's language; the raw value when it is not a day. */
export function formatPriceDate(day: string | null | undefined, lang: string): string | null {
  if (!day) return null;
  const date = new Date(`${day.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(date.getTime())) return day;
  return formatDay(date, lang);
}
