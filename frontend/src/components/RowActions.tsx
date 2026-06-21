// frontend/src/components/RowActions.tsx
// Shared per-row action layout for the resource tables. Keeps the row's primary
// action a visible button and folds the secondary actions (open in editor,
// reveal in Finder, …) into a "⋯" overflow menu so a row never sprawls into a
// wrapping/stacked pile of buttons. Used by the crowded tables (native memory,
// conversations); tables with ≤2 actions still render their buttons inline.
//
// Built on the existing Popover primitive (the kit has no dropdown-menu), with
// controlled open state so a menu item closes the menu when activated.
import { useState, type ReactNode } from "react";
import { MoreHorizontal, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface RowActionItem {
  key: string;
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  destructive?: boolean;
  disabled?: boolean;
}

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
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-9 shrink-0"
              aria-label={menuAriaLabel}
              onClick={(e) => e.stopPropagation()}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-48 p-1">
            {items.map((it) => {
              const Icon = it.icon;
              return (
                <button
                  key={it.key}
                  type="button"
                  disabled={it.disabled}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm",
                    "hover:bg-muted disabled:pointer-events-none disabled:opacity-50",
                    it.destructive && "text-destructive hover:bg-destructive/10",
                  )}
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpen(false);
                    it.onClick();
                  }}
                >
                  {Icon ? <Icon className="size-3.5 shrink-0" /> : null}
                  {it.label}
                </button>
              );
            })}
          </PopoverContent>
        </Popover>
      ) : null}
    </div>
  );
}
