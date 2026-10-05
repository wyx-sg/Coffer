// src/lib/hooks/useGrowingList.ts — a bounded, in-memory list rendered whole, with a safety net for the rare long one.
//
// Every row is already in memory, so a list shows whole. Past RENDER_BATCH rows
// the first batch renders and the rest are added a batch at a time when the end
// of the list scrolls into view (`LoadMoreSentinel`) — one interaction, scroll,
// and no button to press. A list that can really run past ~200 rows is not this
// kind: it pages by cursor (`useInfiniteList`).
import { useState } from "react";

/** Rows rendered at first, and added each time the end of the list is reached. */
export const RENDER_BATCH = 100;

/**
 * The first `RENDER_BATCH` of `items`, growing by a batch per `more()`.
 * `resetKey` (search text, filters) puts the count back to one batch, so a new
 * query never lands halfway down the previous one.
 */
export function useGrowingList<T>(items: readonly T[], resetKey: string) {
  const [count, setCount] = useState(RENDER_BATCH);
  const [lastReset, setLastReset] = useState(resetKey);
  if (lastReset !== resetKey) {
    setLastReset(resetKey);
    setCount(RENDER_BATCH);
  }
  const shown = items.length > count ? items.slice(0, count) : (items as T[]);
  return {
    shown,
    total: items.length,
    hasMore: shown.length < items.length,
    more: () => setCount((c) => c + RENDER_BATCH),
  };
}
