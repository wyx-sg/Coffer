// src/components/usage/RangePill.tsx — the time-range pill: Today · Last 7 days · Last 30 days · This month · Custom range…
//
// "Custom range…" swaps the list for a calendar: dates only, an inclusive
// From–To of local days, then Apply. Per-request detail is kept only for the
// MCP invocation window, so the calendar names the first day that still has it
// (older days keep only daily totals) — a range reaching further back still
// reports, from those.
import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import type { DateRange } from "react-day-picker";
import { useTranslation } from "react-i18next";

import { PILL_TRIGGER } from "@/components/activity/FilterPill";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { UsageQuery } from "@/lib/api/usage";
import { formatDay } from "@/lib/usage/format";
import { PRESET_RANGES, addDays, localDay, parseDay } from "@/lib/usage/range";
import { cn } from "@/lib/utils";

interface Props {
  query: UsageQuery;
  /** Days of per-request detail kept (the `mcp_invocations` policy); null = kept forever. */
  detailDays: number | null;
  onChange: (next: UsageQuery) => void;
}

export function RangePill({ query, detailDays, onChange }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [draft, setDraft] = useState<DateRange | undefined>();
  const today = new Date();
  const custom = query.range === "custom" && query.from && query.to;
  const shown = custom
    ? `${formatDay(parseDay(query.from!), lang, "long")} – ${formatDay(parseDay(query.to!), lang, "long")}`
    : t(`usage.range.${query.range}`);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) setPicking(false);
  };
  const startPicking = () => {
    setDraft(custom ? { from: parseDay(query.from!), to: parseDay(query.to!) } : undefined);
    setPicking(true);
  };
  const field = (label: string, value: Date | undefined, focused: boolean) => (
    <div className="flex flex-1 flex-col gap-1">
      <span className="text-2xs text-text-muted">{label}</span>
      <span
        className={cn(
          "flex h-7 items-center rounded-md border bg-surface-raised px-2 text-xs text-text",
          focused ? "border-accent" : "border-border",
        )}
      >
        {value ? formatDay(value, lang, "date") : "—"}
      </span>
    </div>
  );
  const row = (selected: boolean) =>
    cn(
      "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
      "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
      selected && "bg-surface-selected font-label",
    );

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t("usage.range.label")}
          className={cn(PILL_TRIGGER, open && "bg-surface-selected")}
        >
          <span className="font-label text-text">{shown}</span>
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      {picking ? (
        <PopoverContent
          align="start"
          aria-label={t("usage.range.customTitle")}
          className="flex w-auto max-w-[calc(100vw-2rem)] flex-col gap-2.5 p-3"
        >
          <div className="flex gap-2">
            {field(t("usage.range.from"), draft?.from, !draft?.from || !!draft.to)}
            {field(t("usage.range.to"), draft?.to, !!draft?.from && !draft.to)}
          </div>
          <Calendar
            mode="range"
            selected={draft}
            onSelect={setDraft}
            defaultMonth={draft?.from ?? today}
            disabled={{ after: today }}
            weekStartsOn={1}
          />
          {detailDays !== null ? (
            <p className="max-w-[18rem] text-xs leading-normal text-text-muted">
              {t("usage.range.detailNote", {
                date: formatDay(addDays(today, 1 - detailDays), lang, "long"),
              })}
            </p>
          ) : null}
          <div className="flex justify-end gap-1.5">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              disabled={!draft?.from}
              onClick={() => {
                if (!draft?.from) return;
                onChange({
                  ...query,
                  range: "custom",
                  from: localDay(draft.from),
                  to: localDay(draft.to ?? draft.from),
                });
                setOpen(false);
              }}
            >
              {t("usage.range.apply")}
            </Button>
          </div>
        </PopoverContent>
      ) : (
        <PopoverContent align="start" className="w-52 p-1">
          <div role="listbox" aria-label={t("usage.range.label")} className="flex flex-col">
            {PRESET_RANGES.map((r) => (
              <button
                key={r}
                type="button"
                role="option"
                aria-selected={query.range === r}
                className={row(query.range === r)}
                onClick={() => {
                  onChange({ ...query, range: r, from: undefined, to: undefined });
                  setOpen(false);
                }}
              >
                <span className="min-w-0 flex-1 truncate">{t(`usage.range.${r}`)}</span>
                {query.range === r ? (
                  <Check className="size-3.5 text-accent-text" aria-hidden />
                ) : null}
              </button>
            ))}
            <div className="my-1 border-t border-border-subtle" />
            <button
              type="button"
              role="option"
              aria-selected={query.range === "custom"}
              className={row(query.range === "custom")}
              onClick={startPicking}
            >
              <span className="min-w-0 flex-1 truncate">{t("usage.range.custom")}</span>
              {query.range === "custom" ? (
                <Check className="size-3.5 text-accent-text" aria-hidden />
              ) : null}
            </button>
          </div>
        </PopoverContent>
      )}
    </Popover>
  );
}
