// frontend/src/lib/filters/timeRangeValue.ts
//
// The time-range filter's value (Foundations 0.2.04): one string that lives in
// the URL as `?range=`. A preset is its id ("24h", "7d", "today", "month"); a
// custom range is `<from>..<to>` where each end is a local day "2026-09-29" or
// a local minute "2026-09-29T14:00", and `to` may be "now". Defaults are
// omitted from the URL by the caller via `rangeParam`.

/** Activity keeps 90 days; the picker never reaches further back. */
export const MAX_RANGE_DAYS = 90;

const RANGE_SEP = "..";
const NOW = "now";
const END_RE = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/;

const ROLLING_MS: Record<string, number> = {
  "15m": 900_000,
  "1h": 3_600_000,
  "6h": 21_600_000,
  "24h": 86_400_000,
  "7d": 604_800_000,
  "30d": 2_592_000_000,
};

/** @ui-only A parsed custom range; `to` is "now" or a range end. */
export interface CustomRange {
  from: string;
  to: string;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** "YYYY-MM-DD" (local) for a Date. */
export function dayString(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** A range end for a day and an optional "HH:MM". */
export function makeEnd(day: Date, time?: string): string {
  return time ? `${dayString(day)}T${time}` : dayString(day);
}

/** Parse one range end into a local Date; `dateOnly` says whether no time was given. */
export function parseEnd(end: string): { date: Date; dateOnly: boolean } | undefined {
  const m = END_RE.exec(end);
  if (!m) return undefined;
  const [, y, mo, d, h, mi] = m;
  const date = new Date(Number(y), Number(mo) - 1, Number(d), Number(h ?? 0), Number(mi ?? 0));
  // Reject rolled-over dates like 2026-02-31.
  if (date.getMonth() !== Number(mo) - 1 || date.getDate() !== Number(d)) return undefined;
  if (h !== undefined && (Number(h) > 23 || Number(mi) > 59)) return undefined;
  return { date, dateOnly: h === undefined };
}

/** Split a value into its custom range, or undefined when it is a preset (or malformed). */
export function parseCustom(value: string): CustomRange | undefined {
  const i = value.indexOf(RANGE_SEP);
  if (i < 0) return undefined;
  const from = value.slice(0, i);
  const to = value.slice(i + RANGE_SEP.length);
  if (!parseEnd(from)) return undefined;
  if (to !== NOW && !parseEnd(to)) return undefined;
  return { from, to };
}

export function encodeCustom(range: CustomRange): string {
  return `${range.from}${RANGE_SEP}${range.to}`;
}

/**
 * A value read from the URL, made safe: a known preset id or a well-formed
 * custom range stands as is; anything else becomes `fallback`.
 */
export function normalizeRange(
  raw: string | null | undefined,
  presetIds: readonly string[],
  fallback: string,
): string {
  if (!raw) return fallback;
  if (presetIds.includes(raw)) return raw;
  return parseCustom(raw) ? raw : fallback;
}

/** The `?range=` value to write: undefined (key removed) when it is the default. */
export function rangeParam(value: string, defaultValue: string): string | undefined {
  return value === defaultValue ? undefined : value;
}

export interface ResolvedWindow {
  since?: string;
  until?: string;
}

/** Turn a value into the ISO `since` / `until` the API takes. Unknown ids resolve to no bound. */
export function resolveRange(value: string, now: Date = new Date()): ResolvedWindow {
  const custom = parseCustom(value);
  if (custom) {
    const from = parseEnd(custom.from);
    const since = from?.date.toISOString();
    if (custom.to === NOW) return { since };
    const to = parseEnd(custom.to);
    if (!to) return { since };
    const until = new Date(to.date);
    // A whole day runs to its last millisecond; a typed minute to the end of it.
    if (to.dateOnly) until.setHours(23, 59, 59, 999);
    else until.setSeconds(59, 999);
    return { since, until: until.toISOString() };
  }
  if (value === "today") {
    return { since: new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString() };
  }
  if (value === "month") {
    return { since: new Date(now.getFullYear(), now.getMonth(), 1).toISOString() };
  }
  const ms = ROLLING_MS[value];
  return { since: ms ? new Date(now.getTime() - ms).toISOString() : undefined };
}

/** Earliest day the picker allows (today minus `maxDays`), at local midnight. */
export function earliestDay(now: Date = new Date(), maxDays = MAX_RANGE_DAYS): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - maxDays);
}

/** "Sep 29, 14:00" / "Sep 29" (adds the year when it is not this year). */
function formatEnd(end: string, lang: string, now: Date = new Date()): string {
  const p = parseEnd(end);
  if (!p) return end;
  const opts: Intl.DateTimeFormatOptions =
    p.date.getFullYear() === now.getFullYear()
      ? { month: "short", day: "numeric" }
      : { month: "short", day: "numeric", year: "numeric" };
  const day = p.date.toLocaleDateString(lang, opts);
  return p.dateOnly ? day : `${day}, ${pad(p.date.getHours())}:${pad(p.date.getMinutes())}`;
}

/** A custom range's pill text: "Sep 29, 14:00 – now". */
export function formatCustom(
  range: CustomRange,
  lang: string,
  nowLabel: string,
  now: Date = new Date(),
): string {
  const to = range.to === NOW ? nowLabel : formatEnd(range.to, lang, now);
  return `${formatEnd(range.from, lang, now)} – ${to}`;
}

/** True when `HH:MM` (24 h) is a valid minute of the day. */
export function isTime(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
}
