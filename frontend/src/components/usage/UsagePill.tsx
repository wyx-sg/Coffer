// src/components/usage/UsagePill.tsx — a Usage filter pill: its name, plus the choice when one is made, opening a short list.
//
// Unset it reads just "Agent"; set, "Agent: Claude Code". The list leads with
// the "all" row, so choosing it is how a filter is cleared.
import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";

import { PILL_TRIGGER } from "@/components/activity/FilterPill";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface Option {
  value: string;
  label: string;
}

interface Props {
  /** The filter's name: "Agent". */
  label: string;
  /** The current value, "" when unset. */
  value: string;
  /** The row that clears the filter ("All agents"). */
  allLabel: string;
  options: readonly Option[];
  onChange: (value: string) => void;
}

export function UsagePill({ label, value, allLabel, options, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const chosen = options.find((o) => o.value === value);
  const rows: readonly Option[] = [{ value: "", label: allLabel }, ...options];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(PILL_TRIGGER, (chosen || open) && "bg-surface-selected")}
        >
          <span className={cn(chosen && "text-text-muted")}>{chosen ? `${label}:` : label}</span>
          {chosen ? <span className="font-label text-text">{chosen.label}</span> : null}
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60 p-1" align="start">
        <div role="listbox" aria-label={label} className="flex max-h-80 flex-col overflow-y-auto">
          {rows.map((o) => {
            const selected = o.value === (chosen ? value : "");
            return (
              <button
                key={o.value || "__all"}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
                  "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                  selected && "bg-surface-selected font-label",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {selected ? <Check className="size-3.5 text-accent-text" aria-hidden /> : null}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
