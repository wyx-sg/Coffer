// src/components/filters/pillStyles.ts — the one look every filter pill shares (Foundations 0.2.06).
import { cn } from "@/lib/utils";

/** 26 high · r6 · 1px border; selected = the selected fill (never accent). */
export function pillClass(active: boolean, open: boolean): string {
  return cn(
    "inline-flex h-[26px] shrink-0 items-center gap-1 rounded-[6px] border border-border text-xs",
    "transition-colors duration-fast focus-within:ring-2 focus-within:ring-focus-ring",
    active || open
      ? "bg-surface-selected text-text"
      : "bg-surface-raised font-label text-text-muted hover:bg-surface-hover",
  );
}

/** The pill's own button: padding 10 / 8, no chrome of its own. */
export const PILL_BUTTON =
  "inline-flex h-full min-w-0 items-center gap-1 rounded-[6px] pl-2.5 pr-2 focus-visible:outline-none";
