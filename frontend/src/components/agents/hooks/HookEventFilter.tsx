// src/components/agents/hooks/HookEventFilter.tsx — the Hooks table's Event filter (board 2.1.64).
//
// A button reading "Event  All events" that opens a list: All events, then each
// event with how many of the agent's hooks sit on it. An event with none reads
// muted but can still be chosen (the table then says nothing matches).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface Props {
  /** The chosen event, or null for all. */
  value: string | null;
  onChange: (event: string | null) => void;
  events: readonly string[];
  /** How many hooks sit on each event; the total is `total`. */
  counts: Readonly<Record<string, number>>;
  total: number;
}

export function HookEventFilter({ value, onChange, events, counts, total }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const choose = (next: string | null) => {
    onChange(next);
    setOpen(false);
  };
  const option = (key: string | null, label: string, count: number, mono: boolean) => {
    const selected = value === key;
    return (
      <button
        key={key ?? "all"}
        type="button"
        role="option"
        aria-selected={selected}
        onClick={() => choose(key)}
        className={cn(
          "flex w-full items-center gap-2 rounded-item px-2 py-1.5 text-left text-sm hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
          selected && "bg-surface-hover",
          key !== null && count === 0 && "text-text-muted",
        )}
      >
        <span className="inline-flex size-3.5 shrink-0 items-center justify-center">
          {selected ? <Check className="size-3.5" aria-hidden /> : null}
        </span>
        <span className={cn("min-w-0 flex-1 truncate", mono && "font-mono text-xs")}>{label}</span>
        <span className="text-xs tabular-nums text-text-muted">{count}</span>
      </button>
    );
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" aria-label={t("agents.hooks.own.eventFilter")}>
          <span className="text-text-muted">{t("agents.hooks.own.event")}</span>
          <span className={cn("font-medium", value && "font-mono text-xs")}>
            {value ?? t("agents.hooks.own.allEvents")}
          </span>
          <ChevronDown className="text-text-subtle" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[240px] p-1.5 text-text">
        <div role="listbox" aria-label={t("agents.hooks.own.eventFilter")}>
          {option(null, t("agents.hooks.own.allEvents"), total, false)}
          {events.map((e) => option(e, e, counts[e] ?? 0, true))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
