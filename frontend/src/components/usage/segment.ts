// src/components/usage/segment.ts — the classes of one segment in the Usage page's period control.
import { cn } from "@/lib/utils";

/** A segment of the sunken track: the pressed one is lifted onto the raised surface. */
export function segmentClass(active: boolean): string {
  return cn(
    "h-[22px] whitespace-nowrap rounded-sm px-2.5 text-xs font-label transition-colors duration-fast",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
    active ? "bg-surface-raised text-text shadow-lifted" : "text-text-muted hover:text-text",
  );
}
