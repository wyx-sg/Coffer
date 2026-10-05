// src/components/ui/useProgressiveRows.ts — render a long in-memory list a screenful at a time.
//
// The rows are already fetched whole (a list endpoint that is cheap), so the
// cost is rendering them: the first `initial` rows mount, and `step` more are
// added each time the sentinel under the rows scrolls into view. Selection,
// select-all and search belong to the caller and keep working on the FULL
// array; only what is drawn is sliced. `resetKey` (the search text, a filter)
// puts the count back to `initial`, so a new query never lands halfway down
// the previous one. A list shorter than `initial` renders exactly as before
// and draws no sentinel.
import { createElement, useState, type ReactNode } from "react";

import { LoadMoreSentinel } from "./load-more";

interface Options {
  /** Rows drawn at first. */
  initial?: number;
  /** Rows added each time the end is reached. */
  step?: number;
  /** Changes when the rows are a different view (search, filter): the count starts over. */
  resetKey?: string;
}

interface ProgressiveRows<T> {
  visible: T[];
  hasMore: boolean;
  showMore: () => void;
  /** The scroll trigger to render right under the rows; null when every row is drawn. */
  sentinel: ReactNode;
}

export function useProgressiveRows<T>(
  rows: readonly T[],
  { initial = 50, step = 100, resetKey = "" }: Options = {},
): ProgressiveRows<T> {
  const [count, setCount] = useState(initial);
  const [lastReset, setLastReset] = useState(resetKey);
  if (lastReset !== resetKey) {
    setLastReset(resetKey);
    setCount(initial);
  }
  const hasMore = rows.length > count;
  const visible = hasMore ? rows.slice(0, count) : (rows as T[]);
  const showMore = () => setCount((c) => c + step);
  const sentinel = hasMore
    ? createElement(LoadMoreSentinel, { active: true, onVisible: showMore, version: count })
    : null;
  return { visible, hasMore, showMore, sentinel };
}
