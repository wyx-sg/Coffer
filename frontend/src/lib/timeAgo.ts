// src/lib/timeAgo.ts — how long ago a time was, in the UI's language.

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

/** "2 hours ago" / "2小时前" — how long ago `iso` was, in the UI's language. */
export function timeAgo(iso: string, locale: string, now = Date.now()): string {
  const elapsed = now - new Date(iso).getTime();
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, ms] of UNITS) {
    if (Math.abs(elapsed) >= ms) return rtf.format(-Math.round(elapsed / ms), unit);
  }
  return rtf.format(0, "minute");
}
