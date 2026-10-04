// src/lib/conversations/time.ts
// How the Conversations list places a conversation in time: a group heading
// (Today / Yesterday / Earlier) over rows that each show when they were last
// active: the clock time for today and yesterday, "Sep 22" for earlier. Pure, and told "now",
// so it is unit-tested alone. Day edges are the viewer's local midnight.

/** The groups, newest first. */
const TIME_BUCKETS = ["today", "yesterday", "earlier"] as const;
export type TimeBucket = (typeof TIME_BUCKETS)[number];

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Whole local calendar days from `iso` to `now` (not 24-hour spans, so DST is safe). */
function daysAgo(iso: string, now: Date): number | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const a = startOfDay(now);
  const b = startOfDay(d);
  // Date.UTC over the local Y-M-D makes the difference exact across DST changes.
  const day = (ms: number) => {
    const x = new Date(ms);
    return Date.UTC(x.getFullYear(), x.getMonth(), x.getDate());
  };
  return Math.round((day(a) - day(b)) / 86_400_000);
}

/** The group a timestamp sits in. A timestamp from the future counts as today;
 *  one that does not parse falls into the oldest group. */
export function timeBucket(iso: string, now: Date): TimeBucket {
  const days = daysAgo(iso, now);
  if (days === null) return "earlier";
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return "earlier";
}

export interface TimeGroup<T> {
  bucket: TimeBucket;
  items: T[];
}

/** `items` split into their time groups, newest group first and newest item
 *  first within each; a group with no items is left out. */
export function groupByTime<T>(
  items: readonly T[],
  at: (item: T) => string,
  now: Date,
): TimeGroup<T>[] {
  const stamp = (item: T) => {
    const ms = new Date(at(item)).getTime();
    return Number.isNaN(ms) ? -Infinity : ms;
  };
  const sorted = [...items].sort((x, y) => stamp(y) - stamp(x));
  const groups: TimeGroup<T>[] = [];
  for (const bucket of TIME_BUCKETS) {
    const inBucket = sorted.filter((item) => timeBucket(at(item), now) === bucket);
    if (inBucket.length > 0) groups.push({ bucket, items: inBucket });
  }
  return groups;
}

/** "HH:MM", locale-independent like every other timestamp in the app. */
export function clock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A row's time: "14:10" for today and yesterday, "Sep 22" for earlier ("Sep 22, 2025" in
 *  another year; "9月22日" in Chinese). */
export function rowTime(iso: string, now: Date, lang: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  if (timeBucket(iso, now) !== "earlier") return clock(iso);
  const sameYear = d.getFullYear() === now.getFullYear();
  if (lang.startsWith("zh")) {
    const md = `${d.getMonth() + 1}月${d.getDate()}日`;
    return sameYear ? md : `${d.getFullYear()}年${md}`;
  }
  const md = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  return sameYear ? md : `${md}, ${d.getFullYear()}`;
}
