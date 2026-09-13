// frontend/src/lib/timeRange.ts
//
// Shared time-range vocabulary for the audit (Observability) and MCP
// invocations filters. Both screens offer the same rolling-window presets
// plus a custom From–To window, so the preset table, the local-datetime
// parsing, and the since/until resolution live here once.

/** Rolling-window presets — keys map to `audit.timeRange.*` i18n. */
export const TIME_PRESETS = ["1h", "6h", "24h", "7d", "30d", "all"] as const;

const RANGE_MS: Record<string, number> = {
  "1h": 3_600_000,
  "6h": 21_600_000,
  "24h": 86_400_000,
  "7d": 604_800_000,
  "30d": 2_592_000_000,
};

/** A typed "YYYY-MM-DD HH:mm:ss" (local) -> Date; empty/invalid -> undefined. */
export function parseLocalDate(value: string): Date | undefined {
  const v = value.trim();
  if (!v) return undefined;
  const d = new Date(v.replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? undefined : d;
}

/** A typed "YYYY-MM-DD HH:mm:ss" (local) -> ISO string; empty/invalid -> undefined. */
export function parseLocalDateTime(value: string): string | undefined {
  return parseLocalDate(value)?.toISOString();
}

export interface TimeWindow {
  since?: string;
  until?: string;
}

/**
 * Resolve a `{timeRange, from, to}` filter into a `[since, until]` ISO
 * window. Presets set only `since` (a rolling lower bound); the custom
 * range sets either/both bounds. Both bounds are optional so a custom
 * range with only `from` ("since X") or only `to` ("up to X") works.
 */
export function resolveTimeWindow(f: { timeRange: string; from: string; to: string }): TimeWindow {
  if (f.timeRange === "custom") {
    return { since: parseLocalDateTime(f.from), until: parseLocalDateTime(f.to) };
  }
  const ms = RANGE_MS[f.timeRange];
  return { since: ms ? new Date(Date.now() - ms).toISOString() : undefined };
}
