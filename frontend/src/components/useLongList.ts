// src/components/useLongList.ts — the state behind a "Long" list: five rows, then Show all (see LongList.tsx).
import { useState } from "react";

import { cn } from "@/lib/utils";

export interface LongListOptions {
  /** Rows shown before "Show all". */
  limit?: number;
  /** Cap the expanded list's height and scroll inside it (use in a dialog). */
  scrollInside?: boolean | string;
}

export function useLongList<T>(items: readonly T[], options: LongListOptions = {}) {
  const { limit = 5, scrollInside = false } = options;
  const [expanded, setExpanded] = useState(false);
  const collapsed = !expanded && items.length > limit;
  const visible = collapsed ? items.slice(0, limit) : items;
  const maxHeight = typeof scrollInside === "string" ? scrollInside : "max-h-80";
  return {
    visible,
    shown: visible.length,
    total: items.length,
    /** True while rows are hidden behind "Show all". */
    collapsed,
    expand: () => setExpanded(true),
    /** Classes for the list's container: scrolls inside once expanded. */
    listClassName: cn(expanded && scrollInside && cn(maxHeight, "overflow-y-auto")),
  };
}
