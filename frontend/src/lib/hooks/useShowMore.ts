// src/lib/hooks/useShowMore.ts — a long list rendered in batches: every row is loaded, the DOM grows 50 at a time.
import { useEffect, useState } from "react";

/** How many rows one batch adds. */
const SHOW_MORE_BATCH = 50;

/**
 * The first batch of `items` and a way to reveal the next. `resetKey` (the
 * search text) puts the count back to one batch, so a filter is instant and a
 * new query never lands halfway down a previous one.
 */
export function useShowMore<T>(items: readonly T[], resetKey: string, batch = SHOW_MORE_BATCH) {
  const [count, setCount] = useState(batch);
  useEffect(() => setCount(batch), [resetKey, batch]);
  return {
    shown: items.slice(0, count),
    total: items.length,
    hasMore: count < items.length,
    next: Math.min(batch, items.length - count),
    showMore: () => setCount((c) => c + batch),
  };
}
