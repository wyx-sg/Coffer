// src/lib/usage/range.ts — the Usage tab's range and grouping as URL search params, and local-day arithmetic.
//
// The range is addressable state (a refresh or Back keeps it), so it lives in
// `?range=` as the shared time-range value (a preset id, or custom days
// `2026-09-01..2026-09-20`), with the grouping in `?by=` and the filters in
// `?agent=` (an agent type) and `?provider=` (a connection uid); the defaults
// (7 days, by model, any agent, any provider) are never spelled out. Days are
// the machine's local days, as the summary resolves them.
import type { UsageGroupBy, UsageQuery, UsageRangeName } from "@/lib/api/usage";
import {
  encodeCustom,
  normalizeRange,
  parseCustom,
  parseEnd,
  rangeParam,
} from "@/lib/filters/timeRangeValue";

export const PRESET_RANGES = ["today", "7d", "30d", "month"] as const;
export const GROUPINGS: readonly UsageGroupBy[] = ["model", "provider", "agent", "day"];

/** The tab's own URL params; `writeUsageQuery` owns exactly these. */
const QUERY_KEYS = ["range", "by", "agent", "provider"] as const;
const DEFAULT_RANGE: UsageRangeName = "7d";
const DEFAULT_GROUP: UsageGroupBy = "model";

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

/** The range as the shared pill's value: a preset id or the custom days. */
export function rangeValue(q: UsageQuery): string {
  return q.range === "custom" && q.from && q.to
    ? encodeCustom({ from: q.from, to: q.to })
    : q.range;
}

/** The query's range fields for a pill value; a malformed or reversed custom range is the default. */
export function rangeOf(
  value: string,
  today: Date = new Date(),
): Pick<UsageQuery, "range" | "from" | "to"> {
  const custom = parseCustom(value);
  if (custom) {
    const from = parseEnd(custom.from);
    const to = custom.to === "now" ? { date: today } : parseEnd(custom.to);
    if (from && to) {
      const [first, last] = [localDay(from.date), localDay(to.date)];
      if (first <= last) return { range: "custom", from: first, to: last };
    }
    return { range: DEFAULT_RANGE };
  }
  const preset = (PRESET_RANGES as readonly string[]).includes(value);
  return { range: preset ? (value as UsageRangeName) : DEFAULT_RANGE };
}

/** Read the page's query from the URL; anything malformed falls back to the default. */
export function readUsageQuery(sp: URLSearchParams): UsageQuery {
  const by = sp.get("by");
  const group_by = GROUPINGS.includes(by as UsageGroupBy) ? (by as UsageGroupBy) : DEFAULT_GROUP;
  const agent = sp.get("agent");
  const provider = sp.get("provider");
  const filters = {
    ...(agent ? { agent_type: agent } : {}),
    ...(provider ? { connection_uid: provider } : {}),
  };
  const value = normalizeRange(sp.get("range"), PRESET_RANGES, DEFAULT_RANGE);
  return { ...rangeOf(value), group_by, ...filters };
}

/** The search params for `q`, keeping any unrelated params `sp` carries. */
export function writeUsageQuery(sp: URLSearchParams, q: UsageQuery): URLSearchParams {
  const next = new URLSearchParams(sp);
  for (const k of QUERY_KEYS) next.delete(k);
  const range = rangeParam(rangeValue(q), DEFAULT_RANGE);
  if (range) next.set("range", range);
  if (q.group_by !== DEFAULT_GROUP) next.set("by", q.group_by);
  if (q.agent_type) next.set("agent", q.agent_type);
  if (q.connection_uid) next.set("provider", q.connection_uid);
  return next;
}
