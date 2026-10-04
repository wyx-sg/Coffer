// src/components/agents/list/relativeTime.ts — "2h ago" for a past instant, in the UI language.
//
// The Agents list says when Coffer's hook last delivered; the exact time is in
// the hook's own tab. Intl words it, so no English "ago" leaks into zh.
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** `iso` relative to `now`, e.g. "2h ago" / "2小时前"; under a minute reads "now". */
export function formatRelativeTime(iso: string, language: string, now = Date.now()): string {
  const seconds = Math.round((Date.parse(iso) - now) / 1000);
  const fmt = new Intl.RelativeTimeFormat(language, { numeric: "auto", style: "narrow" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return fmt.format(Math.trunc(seconds / size), unit);
  }
  return fmt.format(0, "second");
}
