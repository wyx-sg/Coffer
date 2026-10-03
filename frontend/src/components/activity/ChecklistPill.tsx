// src/components/activity/ChecklistPill.tsx — a multi-select Activity filter: a pill whose popover is a checklist with counts.
//
// The Agent and Kind filters choose several values at once (design 6.1.03,
// 6.1.04): each row is a checkbox with the value's count, rows can sit in
// labelled groups or be indented under a parent, an optional box narrows a
// long list, and the footer says what is chosen with a Clear. The popover
// stays open while the reader ticks.
import { useState, type ReactNode } from "react";
import { Check, ChevronDown, Minus, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { PILL_TRIGGER } from "./FilterPill";

/** @ui-only One row of the checklist. */
export interface CheckItem {
  value: string;
  /** What the row shows; `text` is its plain words, for the box and the checkbox's name. */
  label: ReactNode;
  text: string;
  count?: number;
  checked: boolean | "mixed";
  /** Sits under the row above it (a change kind under Changes). */
  indent?: boolean;
  /** A top-level row that other rows sit under. */
  strong?: boolean;
}

/** @ui-only A run of rows, optionally under a heading ("Not an agent"). */
export interface CheckGroup {
  label?: string;
  items: CheckItem[];
}

interface Props {
  /** The filter's name, shown before its value: "Agent". */
  label: string;
  /** The chosen values in words, or null for "Any". */
  valueLabel: string | null;
  groups: CheckGroup[];
  onToggle: (value: string) => void;
  onClear: () => void;
  /** What the footer says is chosen ("2 selected"); null hides the footer. */
  summary: string | null;
  /** A box that narrows the rows by their words. */
  searchPlaceholder?: string;
  /** Show just the name ("Source") while nothing is chosen, not "Source: Any". */
  bareWhenEmpty?: boolean;
}

function Box({ checked }: { checked: boolean | "mixed" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-[15px] shrink-0 items-center justify-center rounded-xs",
        checked ? "bg-accent text-accent-foreground" : "border border-input bg-surface-raised",
      )}
    >
      {checked === "mixed" ? (
        <Minus className="size-3" strokeWidth={2.5} />
      ) : checked ? (
        <Check className="size-3" strokeWidth={2.5} />
      ) : null}
    </span>
  );
}

export function ChecklistPill({
  label,
  valueLabel,
  groups,
  onToggle,
  onClear,
  summary,
  searchPlaceholder,
  bareWhenEmpty = false,
}: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = groups
    .map((g) => ({ ...g, items: g.items.filter((i) => i.text.toLowerCase().includes(needle)) }))
    .filter((g) => g.items.length > 0);

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(PILL_TRIGGER, (valueLabel !== null || open) && "bg-surface-selected")}
        >
          {bareWhenEmpty && valueLabel === null ? (
            label
          ) : (
            <>
              {label}:
              <span className="max-w-56 truncate font-label text-text">
                {valueLabel ?? t("activity.filters.any")}
              </span>
            </>
          )}
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-1.5" align="start">
        {searchPlaceholder ? (
          <div className="px-1 pb-1.5 pt-1">
            <label className="flex h-control-md items-center gap-2 rounded-md border border-border bg-surface-raised px-2.5 text-sm text-text focus-within:ring-2 focus-within:ring-focus-ring">
              <Search className="size-3.5 text-text-subtle" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-text-subtle"
              />
            </label>
          </div>
        ) : null}
        <div className="flex max-h-80 flex-col overflow-y-auto">
          {shown.map((group, gi) => (
            <div
              key={group.label ?? gi}
              className={cn(
                "flex flex-col gap-px",
                gi > 0 && "mt-1 border-t border-border-subtle pt-1",
              )}
            >
              {group.label ? (
                <div className="px-2 pb-1 pt-0.5 text-2xs font-semibold text-text-subtle">
                  {group.label}
                </div>
              ) : null}
              {group.items.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  role="checkbox"
                  aria-checked={item.checked === "mixed" ? "mixed" : item.checked}
                  aria-label={item.text}
                  onClick={() => onToggle(item.value)}
                  className={cn(
                    "flex min-h-control-md w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
                    "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                    item.indent && "min-h-7 pl-[31px]",
                    item.strong && "font-label",
                  )}
                >
                  <Box checked={item.checked} />
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.count !== undefined ? (
                    <span className="shrink-0 text-xs font-book text-text-subtle">
                      {item.count.toLocaleString(i18n.language)}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          ))}
          {shown.length === 0 ? (
            <p className="px-2 py-2 text-xs text-text-subtle">{t("activity.filters.noOption")}</p>
          ) : null}
        </div>
        {summary !== null ? (
          <div className="mt-1 flex items-center border-t border-border-subtle px-1.5 pt-1">
            <span className="text-xs text-text-muted">{summary}</span>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={onClear}>
              {t("activity.filters.clear")}
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
