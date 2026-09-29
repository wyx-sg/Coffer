// src/components/agents/sessions/sessionTime.ts — how long ago a session was active, and when it ran.
// The list shows a compact age ("2h", "3d"); the reader shows the date and the
// time range the session spanned. Dates go through `formatDateTime` so the page
// keeps the app's one locale-independent format.
import { formatDateTime } from "@/lib/utils";

type Age =
  | { unit: "now" }
  | { unit: "minutes" | "hours" | "days" | "weeks"; count: number }
  | { unit: "date"; date: string };

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

/** The age of `iso` at `now`, in the largest whole unit up to five weeks, then its date. */
export function ageOf(iso: string, now: number = Date.now()): Age {
  const elapsed = now - new Date(iso).getTime();
  if (Number.isNaN(elapsed) || elapsed >= 5 * WEEK) {
    return { unit: "date", date: formatDateTime(iso).slice(0, 10) };
  }
  if (elapsed < MINUTE) return { unit: "now" };
  if (elapsed < HOUR) return { unit: "minutes", count: Math.floor(elapsed / MINUTE) };
  if (elapsed < DAY) return { unit: "hours", count: Math.floor(elapsed / HOUR) };
  if (elapsed < WEEK) return { unit: "days", count: Math.floor(elapsed / DAY) };
  return { unit: "weeks", count: Math.floor(elapsed / WEEK) };
}

/** "2026-09-28 09:41–10:22", or both ends in full when the session crossed midnight. */
export function timeRange(started: string | null, last: string | null): string | null {
  const from = started ?? last;
  if (!from) return null;
  const start = formatDateTime(from).slice(0, 16);
  if (!last || last === from) return start;
  const end = formatDateTime(last).slice(0, 16);
  return end.slice(0, 10) === start.slice(0, 10)
    ? `${start}–${end.slice(11)}`
    : `${start} – ${end}`;
}

/** The last segment of a project path — what the list names a project by. */
export function projectName(path: string | null): string | null {
  if (!path) return null;
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}
