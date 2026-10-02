// frontend/src/components/channel/channelTurnSettings.ts
// The per-channel turn settings a channel's Settings tab holds as typed text:
// the two message-batching windows, the two reply settings (step list,
// completion ping) and the idle period that opens a new conversation. Each has
// a parser for what the user typed and the bounds it is checked against.
//
// There are no defaults here. A channel's values — defaults included — come
// from the daemon's typed reading of its configuration (`status.settings`, the
// channels contract's `ChannelSettings`), so a default is written in one place.

export const BURST_WAIT_MIN = 0;
export const BURST_WAIT_MAX = 60;

/** Parse what the user typed into a batching field: seconds in [0, 60], or
 *  null for anything else (blank, not a number, out of range). */
export function parseBurstWait(text: string): number | null {
  return parseInRange(text, BURST_WAIT_MIN, BURST_WAIT_MAX);
}

/** The completion-ping threshold's bounds, in seconds (0 turns the ping off). */
export const NOTIFY_AFTER_MIN = 0;
export const NOTIFY_AFTER_MAX = 3600;

/** Parse the ping threshold as typed: seconds in [0, 3600], or null for
 *  anything else (blank, not a number, out of range). */
export function parseNotifyAfter(text: string): number | null {
  return parseInRange(text, NOTIFY_AFTER_MIN, NOTIFY_AFTER_MAX);
}

/** The idle period's bounds, in hours (0 never opens a new conversation). */
export const IDLE_HOURS_MIN = 0;
export const IDLE_HOURS_MAX = 8760;

/** Parse the idle period as typed: hours in [0, 8760], or null for anything
 *  else (blank, not a number, out of range). */
export function parseIdleHours(text: string): number | null {
  return parseInRange(text, IDLE_HOURS_MIN, IDLE_HOURS_MAX);
}

function parseInRange(text: string, min: number, max: number): number | null {
  if (text.trim() === "") return null;
  const n = Number(text);
  if (!Number.isFinite(n) || n < min || n > max) return null;
  return n;
}
