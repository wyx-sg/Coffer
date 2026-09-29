// src/lib/overview/time.ts — the short times the Overview prints: "09:12", "yesterday", or a date.
//
// Built on formatDateTime so every timestamp in the app reads the same
// ("YYYY-MM-DD HH:mm:ss" in local time); the Overview only keeps the part a
// glance needs.
import { formatDateTime } from "@/lib/utils";

/** @ui-only How long ago something started, as the "Since …" label needs it. */
export type SinceLabel =
  | { kind: "today"; time: string }
  | { kind: "yesterday" }
  | { kind: "date"; date: string };

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** "HH:mm" in local time. */
export function formatClock(iso: string): string {
  return formatDateTime(iso).slice(11, 16);
}

/** Today → its time, the day before → yesterday, else the date; null for no or a malformed time. */
export function describeSince(iso: string | null, now: Date = new Date()): SinceLabel | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  if (sameDay(at, now)) return { kind: "today", time: formatClock(iso) };
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(at, yesterday)) return { kind: "yesterday" };
  return { kind: "date", date: formatDateTime(iso).slice(0, 10) };
}

/** A row's time: "HH:mm" today, "YYYY-MM-DD HH:mm" before. */
export function formatShortTime(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return sameDay(at, now) ? formatClock(iso) : formatDateTime(iso).slice(0, 16);
}
