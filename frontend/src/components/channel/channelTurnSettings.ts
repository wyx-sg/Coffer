// frontend/src/components/channel/channelTurnSettings.ts
// The per-channel turn settings a channel's Settings tab holds as typed text:
// the two message-batching windows and the two reply settings (step list,
// completion ping). Each has the backend's default for an absent key, a
// reader for the stored value, and a parser for what the user typed.

/**
 * The two message-batching windows — spec channels "Take a burst of messages
 * as one turn". The defaults are the backend's, used when the config key is
 * absent; 0 means "don't wait" (every message is its own turn).
 */
export const BURST_WAIT_DEFAULTS = {
  wait_after_text_seconds: 1.5,
  wait_after_forward_seconds: 5,
} as const;
export type BurstWaitKey = keyof typeof BURST_WAIT_DEFAULTS;
export const BURST_WAIT_MIN = 0;
export const BURST_WAIT_MAX = 60;

/** A stored batching window, or the backend default when absent / not a number. */
export function storedBurstWait(config: Record<string, unknown>, key: BurstWaitKey): number {
  const v = config[key];
  return typeof v === "number" && Number.isFinite(v) ? v : BURST_WAIT_DEFAULTS[key];
}

/** Parse what the user typed into a batching field: seconds in [0, 60], or
 *  null for anything else (blank, not a number, out of range). */
export function parseBurstWait(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text);
  if (!Number.isFinite(n) || n < BURST_WAIT_MIN || n > BURST_WAIT_MAX) return null;
  return n;
}

/**
 * The two reply settings. The defaults are the backend's, used when the key is
 * absent: steps are listed, and a turn of 90s or longer pings when it ends.
 */
const SHOW_STEPS_DEFAULT = true;
const NOTIFY_AFTER_DEFAULT = 90;
export const NOTIFY_AFTER_MIN = 0;
export const NOTIFY_AFTER_MAX = 3600;

/** The stored show-steps switch, or the backend default when absent. */
export function storedShowSteps(config: Record<string, unknown>): boolean {
  const v = config.show_steps;
  return typeof v === "boolean" ? v : SHOW_STEPS_DEFAULT;
}

/** The stored completion-ping threshold, or the backend default when absent. */
export function storedNotifyAfter(config: Record<string, unknown>): number {
  const v = config.notify_after_seconds;
  return typeof v === "number" && Number.isFinite(v) ? v : NOTIFY_AFTER_DEFAULT;
}

/** Parse the ping threshold as typed: seconds in [0, 3600], or null for
 *  anything else (blank, not a number, out of range). */
export function parseNotifyAfter(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text);
  if (!Number.isFinite(n) || n < NOTIFY_AFTER_MIN || n > NOTIFY_AFTER_MAX) return null;
  return n;
}
