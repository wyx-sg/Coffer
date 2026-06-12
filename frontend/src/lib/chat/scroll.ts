// src/lib/chat/scroll.ts
// Scroll helpers for the message thread. Kept pure + framework-free so the
// "should we auto-scroll?" decision is unit-testable without a layout engine.

/**
 * True when the scroll position is within `threshold` px of the bottom.
 * Used to decide whether a new message/token should auto-scroll: we only
 * follow the stream when the user is already at the bottom, so scrolling up
 * to read history during a stream is never yanked back down.
 */
export function isNearBottom(
  el: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">,
  threshold = 80,
): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}
