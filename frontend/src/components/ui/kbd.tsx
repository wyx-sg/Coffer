// src/components/ui/kbd.tsx
// A key cap (Foundations-Selection "Kbd"): 18 high, 5 across, radius 4, 11 in text-subtle on the raised surface.
import * as React from "react";

import { cn } from "@/lib/utils";

/** One key or chord (`⌘K`, `/`, `esc`). Decorative next to a label that already
 *  names the action; pass `aria-hidden` there. */
export function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center rounded-xs border border-border bg-surface-raised px-[5px] font-sans text-2xs text-text-subtle",
        className,
      )}
      {...props}
    />
  );
}
