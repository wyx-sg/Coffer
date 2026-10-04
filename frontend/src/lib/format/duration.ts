// src/lib/format/duration.ts — how long a turn or a tool call took, as the
// Conversations page words it: "42s" under a minute, "1m 08s" from a minute on
// (Run canvas 3.1.06). Pure, so the thresholds are unit-tested alone.

/** A turn's length: whole seconds under a minute ("42s"), else "1m 08s". */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}m ${seconds}s`;
}

/** A tool call's length: tenths of a second under ten ("0.3s"), else as a turn's. */
export function formatToolDuration(ms: number): string {
  if (ms >= 10_000) return formatDuration(ms);
  const tenths = Math.max(0, Math.round(ms / 100));
  return `${(tenths / 10).toFixed(1)}s`;
}

/** Milliseconds between two ISO timestamps, or null when either is missing or unreadable. */
export function elapsedMs(from: string | null | undefined, to: string | null | undefined) {
  if (!from || !to) return null;
  const a = new Date(from).getTime();
  const b = new Date(to).getTime();
  return Number.isNaN(a) || Number.isNaN(b) ? null : Math.max(0, b - a);
}
