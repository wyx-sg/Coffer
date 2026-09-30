// src/lib/usage/range.ts — the Usage page's range and grouping as URL search params, and local-day arithmetic.
//
// The range is addressable state (a refresh or Back keeps it), so it lives in
// `?range=` / `?from=&to=` / `?by=`; the defaults (7 days, by model) are never
// spelled out. Days are the machine's local days, as the summary resolves them.
import type { UsageGroupBy, UsageQuery, UsageRangeName } from "@/lib/api/usage";

export const PRESET_RANGES = ["today", "7d", "30d", "month"] as const;
export const GROUPINGS: readonly UsageGroupBy[] = ["model", "agent", "day"];

const DEFAULT_RANGE: UsageRangeName = "7d";
const DEFAULT_GROUP: UsageGroupBy = "model";
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Is `s` a real `YYYY-MM-DD` day? */
export function isDay(s: string | null | undefined): s is string {
  return !!s && DAY.test(s) && !Number.isNaN(parseDay(s).getTime());
}

/** Local midnight of a `YYYY-MM-DD` day. */
export function parseDay(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** The local `YYYY-MM-DD` of a date. */
export function localDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function addDays(d: Date, days: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
}

/** Every local day from `start` to `end`, both included (empty when reversed). */
export function daysBetween(start: string, end: string): string[] {
  const out: string[] = [];
  const last = parseDay(end).getTime();
  for (let d = parseDay(start); d.getTime() <= last; d = addDays(d, 1)) out.push(localDay(d));
  return out;
}

/** Read the page's query from the URL; anything malformed falls back to the default. */
export function readUsageQuery(sp: URLSearchParams): UsageQuery {
  const by = sp.get("by");
  const group_by = GROUPINGS.includes(by as UsageGroupBy) ? (by as UsageGroupBy) : DEFAULT_GROUP;
  const range = sp.get("range");
  const from = sp.get("from");
  const to = sp.get("to");
  if (range === "custom" && isDay(from) && isDay(to) && from <= to) {
    return { range: "custom", from, to, group_by };
  }
  const preset = (PRESET_RANGES as readonly string[]).includes(range ?? "")
    ? (range as UsageRangeName)
    : DEFAULT_RANGE;
  return { range: preset, group_by };
}

/** The search params for `q`, keeping any unrelated params `sp` carries. */
export function writeUsageQuery(sp: URLSearchParams, q: UsageQuery): URLSearchParams {
  const next = new URLSearchParams(sp);
  for (const k of ["range", "from", "to", "by"]) next.delete(k);
  if (q.range !== DEFAULT_RANGE) next.set("range", q.range);
  if (q.range === "custom" && q.from && q.to) {
    next.set("from", q.from);
    next.set("to", q.to);
  }
  if (q.group_by !== DEFAULT_GROUP) next.set("by", q.group_by);
  return next;
}
