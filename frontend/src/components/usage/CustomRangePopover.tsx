// src/components/usage/CustomRangePopover.tsx — "Custom…": pick an inclusive From–To of local days, then Apply.
//
// Per-request detail is kept only for the MCP invocation window, so the
// popover names the first day that still has it (older days keep only daily
// totals) — a custom range reaching further back still reports, from those.
import { useState } from "react";
import type { DateRange } from "react-day-picker";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatDay } from "@/lib/usage/format";
import { addDays, localDay, parseDay } from "@/lib/usage/range";
import { cn } from "@/lib/utils";
import { segmentClass } from "./segment";

interface Props {
  /** The committed custom range, when the page is on one. */
  from?: string;
  to?: string;
  active: boolean;
  /** Days of per-request detail kept (the `mcp_invocations` policy); null = kept forever. */
  detailDays: number | null;
  onApply: (from: string, to: string) => void;
}

export function CustomRangePopover({ from, to, active, detailDays, onApply }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DateRange | undefined>();
  const today = new Date();

  const onOpenChange = (next: boolean) => {
    if (next) setDraft(from && to ? { from: parseDay(from), to: parseDay(to) } : undefined);
    setOpen(next);
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
  const label =
    active && from && to
      ? `${formatDay(parseDay(from), lang, "long")} – ${formatDay(parseDay(to), lang, "long")}`
      : t("usage.providers.range.custom");

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button type="button" aria-pressed={active} className={segmentClass(active)}>
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        aria-label={t("usage.providers.customRange")}
        className="flex w-auto max-w-[calc(100vw-2rem)] flex-col gap-2.5 p-3"
      >
        <div className="flex gap-2">
          {field(t("usage.providers.from"), draft?.from, !draft?.from || !!draft.to)}
          {field(t("usage.providers.to"), draft?.to, !!draft?.from && !draft.to)}
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
            {t("usage.providers.detailNote", {
              date: formatDay(addDays(today, 1 - detailDays), lang, "long"),
            })}
          </p>
        ) : null}
        <div className="flex justify-end gap-1.5">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            disabled={!draft?.from}
            onClick={() => {
              if (!draft?.from) return;
              onApply(localDay(draft.from), localDay(draft.to ?? draft.from));
              setOpen(false);
            }}
          >
            {t("usage.providers.apply")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
