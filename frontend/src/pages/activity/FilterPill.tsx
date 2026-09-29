// src/pages/activity/FilterPill.tsx — one Activity filter as a pill ("Agent: Any") that opens a list of choices.
//
// Activity's filters are pills with popovers (design 6.1): the pill names the
// filter and its current choice, and the popover lists the choices in groups,
// each optionally carrying a count. Choosing one closes the popover; "Clear"
// returns the filter to its "any" value.
import { useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** @ui-only One choice in a pill's list. */
export interface PillOption {
  value: string;
  label: ReactNode;
}

/** @ui-only A labelled run of choices ("Not an agent"). */
export interface PillGroup {
  label?: string;
  options: PillOption[];
}

interface Props {
  /** The filter's name, shown before its value: "Agent". */
  label: string;
  value: string;
  /** The value that means "no filter". */
  anyValue: string;
  groups: PillGroup[];
  onChange: (value: string) => void;
  /** The pill's text when nothing is chosen ("Any"). */
  anyLabel?: string;
}

export function FilterPill({ label, value, anyValue, groups, onChange, anyLabel }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const all = groups.flatMap((g) => g.options);
  const chosen = all.find((o) => o.value === value);
  const shown =
    value === anyValue || !chosen ? (anyLabel ?? t("activity.filters.any")) : chosen.label;

  const choose = (next: string) => {
    onChange(next);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-control-sm shrink-0 items-center gap-1 rounded-md border border-border bg-surface-raised px-2 text-xs text-text-muted",
            "transition-colors duration-fast hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            value !== anyValue && "bg-surface-selected",
          )}
        >
          {label}:<span className="font-label text-text">{shown}</span>
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60 p-1" align="start">
        <div role="listbox" aria-label={label} className="flex max-h-80 flex-col overflow-y-auto">
          {groups.map((group, gi) => (
            <div
              key={group.label ?? gi}
              className={cn(gi > 0 && "mt-1 border-t border-border-subtle pt-1")}
            >
              {group.label ? (
                <div className="px-2 pb-0.5 pt-1 text-2xs font-semibold text-text-subtle">
                  {group.label}
                </div>
              ) : null}
              {group.options.map((option) => {
                const selected = option.value === value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => choose(option.value)}
                    className={cn(
                      "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
                      "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                      selected && "bg-surface-selected font-label",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{option.label}</span>
                    {selected ? <Check className="size-3.5 text-accent-text" aria-hidden /> : null}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        {value !== anyValue ? (
          <div className="mt-1 border-t border-border-subtle px-1 pt-1">
            <button
              type="button"
              onClick={() => choose(anyValue)}
              className="h-7 w-full rounded-sm px-1 text-left text-xs text-text-muted hover:bg-surface-hover hover:text-text"
            >
              {t("activity.filters.clear")}
            </button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
