// src/components/ui/menu.tsx
// An action menu (the "⋯" on an agent row and the agent header) over the Popover primitive.
//
// A small list of commands, each a `role="menuitem"` button; arrow keys move
// between items, Home / End jump, Escape closes and focus returns to the
// trigger (Radix Popover). Choosing an item closes the menu before running it,
// so a dialog the item opens takes focus cleanly. Destructive items read in the
// danger role; a separator groups them apart.
import * as React from "react";
import { MoreHorizontal, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface MenuAction {
  key: string;
  label: string;
  /** A second, muted line saying what the item does, for a choice that is not obvious. */
  description?: string;
  icon?: LucideIcon;
  onSelect: () => void;
  destructive?: boolean;
  disabled?: boolean;
  /** Draw a separator above this item. */
  separated?: boolean;
  /** The key that runs it elsewhere on the page (e.g. "⌘E"), shown right. */
  shortcut?: string;
}

interface Props {
  /** The trigger's accessible name, e.g. "More actions for Codex". */
  label: string;
  actions: readonly MenuAction[];
  align?: "start" | "center" | "end";
  className?: string;
}

export function ActionMenu({ label, actions, align = "end", className }: Props) {
  const [open, setOpen] = React.useState(false);
  const listRef = React.useRef<HTMLDivElement>(null);

  const items = () =>
    Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([disabled])') ??
        [],
    );

  const onKeyDown = (event: React.KeyboardEvent) => {
    const all = items();
    if (all.length === 0) return;
    const index = all.indexOf(document.activeElement as HTMLButtonElement);
    let next = -1;
    if (event.key === "ArrowDown") next = (index + 1) % all.length;
    else if (event.key === "ArrowUp") next = (index - 1 + all.length) % all.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = all.length - 1;
    if (next < 0) return;
    event.preventDefault();
    all[next].focus();
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          aria-haspopup="menu"
          className={className}
          onClick={(event) => event.stopPropagation()}
        >
          <MoreHorizontal className="size-4" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align={align}
        className="w-auto min-w-[180px] p-1"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          items()[0]?.focus();
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          ref={listRef}
          role="menu"
          aria-label={label}
          onKeyDown={onKeyDown}
          className="flex flex-col"
        >
          {actions.map((action) => {
            const Icon = action.icon;
            return (
              <React.Fragment key={action.key}>
                {action.separated ? (
                  <div role="separator" className="my-1 h-px bg-border-subtle" />
                ) : null}
                <button
                  type="button"
                  role="menuitem"
                  disabled={action.disabled}
                  onClick={() => {
                    setOpen(false);
                    action.onSelect();
                  }}
                  // Foundations-Overlays "Menu": item 30 high, 8 across, r6,
                  // 13/400, a 14px text-muted icon 9 before the label, the
                  // shortcut 11 text-muted on the right; danger reads danger.
                  className={cn(
                    "flex items-center gap-[9px] rounded-item px-2 text-left text-sm font-normal outline-none transition-colors duration-fast",
                    "hover:bg-surface-hover focus-visible:bg-surface-hover disabled:pointer-events-none disabled:opacity-disabled",
                    action.description ? "min-h-control-md py-1.5" : "h-control-md",
                    action.destructive ? "text-danger" : "text-text",
                  )}
                >
                  {Icon ? (
                    <Icon
                      className={cn(
                        "size-3.5 shrink-0",
                        action.destructive ? "text-danger" : "text-text-muted",
                      )}
                      aria-hidden
                    />
                  ) : null}
                  {action.description ? (
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate">{action.label}</span>
                      <span className="text-2xs leading-snug text-text-muted">
                        {action.description}
                      </span>
                    </span>
                  ) : (
                    <span className="min-w-0 flex-1 truncate">{action.label}</span>
                  )}
                  {action.shortcut ? (
                    <span aria-hidden className="ml-3 shrink-0 text-2xs text-text-muted">
                      {action.shortcut}
                    </span>
                  ) : null}
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
