// src/components/RowActions.tsx — shared per-row action layout for the resource
// tables. Keeps the row's primary action a visible button and folds the
// secondary actions (open in editor, reveal in Finder, …) into a "⋯" overflow
// menu so a row never sprawls into a wrapping/stacked pile of buttons. Used by
// the crowded tables (native memory, conversations); tables with ≤2 actions
// still render their buttons inline.
//
// Built on the DropdownMenu primitive so the overflow is a real role="menu":
// arrow keys move between items, Escape closes, focus returns to the trigger.
import { useState, type MouseEvent, type ReactNode } from "react";
import { MoreHorizontal, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface RowActionItem {
  key: string;
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  destructive?: boolean;
  disabled?: boolean;
}

// The rows these menus sit in are often clickable (navigate on click); the
// menu is portaled, but React still bubbles the synthetic event up the
// component tree, so every interaction inside stops propagation.
const stop = (e: MouseEvent) => e.stopPropagation();

export function RowActions({
  primary,
  items,
  menuAriaLabel,
}: {
  /** The always-visible primary action(s) for the row. */
  primary?: ReactNode;
  /** Secondary actions folded into the "⋯" menu; menu hidden when empty. */
  items: RowActionItem[];
  /** Accessible label for the overflow trigger. */
  menuAriaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex items-start justify-end gap-2">
      {primary}
      {items.length > 0 ? (
        <DropdownMenu open={open} onOpenChange={setOpen}>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              size="icon-md"
              variant="ghost"
              className="shrink-0"
              aria-label={menuAriaLabel}
              onClick={(e) => {
                stop(e);
                // Radix opens the menu on pointerdown. A programmatic click
                // (assistive tech, `element.click()`) carries no pointer
                // event and reports detail 0 — open on that too, so activation
                // never depends on how the click was produced.
                if (e.detail === 0) setOpen(true);
              }}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48" onClick={stop}>
            {items.map((it) => {
              const Icon = it.icon;
              return (
                <DropdownMenuItem
                  key={it.key}
                  disabled={it.disabled}
                  onSelect={it.onClick}
                  className={cn(
                    it.destructive &&
                      "text-destructive focus:bg-destructive/10 focus:text-destructive",
                  )}
                >
                  {Icon ? <Icon className="size-3.5 shrink-0" /> : null}
                  {it.label}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}
