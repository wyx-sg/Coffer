// src/lib/usage/format.ts — how the Usage page writes numbers, money, clock times and days, per UI language.
//
// Pure functions over `Intl`, so the tiles, the chart and the table agree and
// each rule is unit-tested without a component. English days are assembled
// day-first ("Wed 23 Sep", as the design writes them) from en-US's own parts;
// Chinese uses zh-CN's forms whole.

/** The Intl locale for an i18next language. */
function intlLocale(lang: string): string {
  return lang.startsWith("zh") ? "zh-CN" : "en-US";
}

/** A whole count with grouping: 3,092. */
export function formatCount(n: number, lang: string): string {
  return new Intl.NumberFormat(intlLocale(lang)).format(n);
}

/** A token count, compact to three significant digits from a thousand up: 6.00M, 696K, 27.0M. */
export function formatTokens(n: number, lang: string): string {
  if (Math.abs(n) < 1000) return formatCount(n, lang);
  return new Intl.NumberFormat(intlLocale(lang), {
    notation: "compact",
    minimumSignificantDigits: 3,
    maximumSignificantDigits: 3,
  }).format(n);
}

/** Dollars to the cent: $25.81; a cost under a cent that is not zero reads "<$0.01". */
export function formatCost(usd: number, lang: string, fractionDigits = 2): string {
  const fmt = new Intl.NumberFormat(intlLocale(lang), {
    style: "currency",
    currency: "USD",
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
  if (usd > 0 && usd < 0.01 && fractionDigits === 2) return `<${fmt.format(0.01)}`;
  return fmt.format(usd);
}

/** Whether no request of `totals` was priced, so its cost is unknown — never shown as $0.00. */
export function allUnpriced(totals: { requests: number; unpriced_requests: number }): boolean {
  return totals.requests > 0 && totals.unpriced_requests >= totals.requests;
}

/**
 * A local day for display. `short` is the chart's axis for a short range
 * ("Wed 23"), `long` the table and tooltip ("Wed Sep 23"), `month` the axis of
 * a long range ("Sep 23").
 */
export function formatDay(day: Date, lang: string, style: "short" | "long" | "month"): string {
  const options: Intl.DateTimeFormatOptions =
    style === "short"
      ? { weekday: "short", day: "numeric" }
      : style === "long"
        ? { weekday: "short", day: "numeric", month: "short" }
        : { day: "numeric", month: "short" };
  const fmt = new Intl.DateTimeFormat(intlLocale(lang), options);
  if (lang.startsWith("zh")) return fmt.format(day);
  const part = Object.fromEntries(fmt.formatToParts(day).map((p) => [p.type, p.value]));
  const order =
    style === "short"
      ? [part.weekday, part.day]
      : style === "long"
        ? [part.weekday, part.month, part.day]
        : [part.month, part.day];
  return order.join(" ");
}

/** A span split into whole days, hours and minutes (negative spans are zero). */
export function splitDuration(ms: number): { days: number; hours: number; minutes: number } {
  const minutesTotal = Math.max(0, Math.floor(ms / 60_000));
  return {
    days: Math.floor(minutesTotal / 1440),
    hours: Math.floor((minutesTotal % 1440) / 60),
    minutes: minutesTotal % 60,
  };
}

const STEPS = [1, 2, 5, 10];

/** A y-axis for values up to `max`: the smallest round step (1, 2 or 5 × 10ⁿ)
 *  that covers it in at most four intervals, and the ticks from 0. */
export function niceTicks(max: number): { step: number; ticks: number[] } {
  if (!(max > 0)) return { step: 1, ticks: [0, 1] };
  const magnitude = 10 ** Math.floor(Math.log10(max / 4));
  const step = (STEPS.find((s) => Math.ceil(max / (s * magnitude) - 1e-9) <= 4) ?? 10) * magnitude;
  const count = Math.max(1, Math.ceil(max / step - 1e-9));
  const ticks = Array.from({ length: count + 1 }, (_, i) => Number((i * step).toFixed(6)));
  return { step, ticks };
}
