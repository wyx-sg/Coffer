// src/components/DetailTabsMore.tsx — a detail page's tab strip with a "More ⌄" overflow.
//
// Foundations rule for the tab overflow: the tabs that fit (six) sit in the
// strip and the least used go in More. When the open tab lives in More, the
// trigger takes that tab's name, keeps its chevron and carries the underline,
// so the strip always shows where you are. When a tab inside More needs
// attention, More carries a warning dot. Renders inside a Radix `Tabs` root;
// choosing a tab from the menu calls `onSelect`, which is the root's setter.
import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export interface DetailTab {
  id: string;
  label: string;
  /** The tab holds something that needs the user (a warning dot on More while it is hidden). */
  attention?: boolean;
}

interface Props {
  /** The tabs shown in the strip, in order. */
  tabs: readonly DetailTab[];
  /** The tabs behind More, in order. */
  more: readonly DetailTab[];
  /** The open tab's id. */
  value: string;
  onSelect: (id: string) => void;
  /** The word on the overflow trigger while no hidden tab is open. */
  moreLabel: string;
  className?: string;
}

export function DetailTabsMore({ tabs, more, value, onSelect, moreLabel, className }: Props) {
  const [open, setOpen] = useState(false);
  const openMore = more.find((tab) => tab.id === value);
  const attention = more.some((tab) => tab.attention);

  return (
    <TabsList className={className}>
      {tabs.map((tab) => (
        <TabsTrigger key={tab.id} value={tab.id}>
          {tab.label}
        </TabsTrigger>
      ))}
      {more.length > 0 ? (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-haspopup="menu"
              data-state={openMore ? "active" : "inactive"}
              className={cn(
                "group relative -mb-px inline-flex items-center gap-1 whitespace-nowrap border-b-2 border-transparent text-sm font-book text-text-muted outline-none transition-colors duration-fast hover:text-text",
                openMore && "border-text font-label text-text",
              )}
            >
              <span className="inline-flex items-center gap-1 rounded-xs px-0.5 group-focus-visible:ring-2 group-focus-visible:ring-focus-ring">
                {openMore ? openMore.label : moreLabel}
                <ChevronDown className="size-3" aria-hidden />
                {attention ? (
                  <span aria-hidden className="ml-0.5 size-1.5 rounded-full bg-warning" />
                ) : null}
              </span>
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-auto min-w-[160px] p-1">
            <div role="menu" aria-label={moreLabel} className="flex flex-col">
              {more.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    onSelect(tab.id);
                  }}
                  className={cn(
                    "flex h-control-md w-full items-center gap-2 rounded-item px-2 text-left text-sm text-text outline-none hover:bg-surface-hover focus-visible:bg-surface-hover",
                    tab.id === value ? "font-label" : "font-normal",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate">{tab.label}</span>
                  {tab.attention ? (
                    <span aria-hidden className="size-1.5 rounded-full bg-warning" />
                  ) : null}
                </button>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      ) : null}
    </TabsList>
  );
}
