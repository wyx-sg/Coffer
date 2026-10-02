// src/components/activity/ActivityTimeRange.tsx — Activity's time window: a pill whose popover lists the windows and a custom range.
//
// Design 6.1.05: five windows — the last 15 minutes, hour, 24 hours, 7 days,
// or everything the retention settings keep — then a custom From / To, where
// an empty To means now, applied with "Apply range".
import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { parseLocalDate } from "@/lib/timeRange";
import { cn } from "@/lib/utils";
import { PILL_TRIGGER } from "./FilterPill";

/** The windows the picker offers, shortest first; "all" is everything kept. */
const ACTIVITY_TIME_PRESETS = ["15m", "1h", "24h", "7d", "all"] as const;

/** @ui-only The time window as the filters hold it. */
interface TimeRangeValue {
  timeRange: string;
  from: string;
  to: string;
}

interface Props extends TimeRangeValue {
  onChange: (next: TimeRangeValue) => void;
}

/** The pill's words for a window: "Last hour", or "13:00 → now" for a custom one. */
export function useTimeRangeLabel({ timeRange, from, to }: TimeRangeValue): string {
  const { t } = useTranslation();
  if (timeRange !== "custom") return t(`activity.time.${timeRange}`, { defaultValue: timeRange });
  return t("activity.time.customLabel", {
    from: from || t("activity.time.start"),
    to: to || t("activity.time.now"),
  });
}

export function ActivityTimeRange({ timeRange, from, to, onChange }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draftFrom, setDraftFrom] = useState(from);
  const [draftTo, setDraftTo] = useState(to);
  const label = useTimeRangeLabel({ timeRange, from, to });

  const fromInvalid = draftFrom.trim() !== "" && !parseLocalDate(draftFrom);
  const toInvalid = draftTo.trim() !== "" && !parseLocalDate(draftTo);
  const empty = draftFrom.trim() === "" && draftTo.trim() === "";

  const choose = (preset: string) => {
    onChange({ timeRange: preset, from: "", to: "" });
    setOpen(false);
  };
  const apply = () => {
    onChange({ timeRange: "custom", from: draftFrom.trim(), to: draftTo.trim() });
    setOpen(false);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setDraftFrom(from);
          setDraftTo(to);
        }
        setOpen(next);
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t("activity.time.label", { range: label })}
          className={cn(PILL_TRIGGER, open && "bg-surface-selected")}
        >
          {label}
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-1.5" align="start">
        <div
          role="listbox"
          aria-label={t("activity.time.heading")}
          className="flex flex-col gap-px"
        >
          {ACTIVITY_TIME_PRESETS.map((preset) => {
            const selected = timeRange === preset;
            return (
              <button
                key={preset}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => choose(preset)}
                className={cn(
                  "flex min-h-control-md items-center gap-2 rounded-sm px-2.5 text-left text-sm text-text",
                  "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                  selected && "bg-surface-selected",
                )}
              >
                {t(`activity.time.${preset}`)}
                {selected ? (
                  <Check className="ml-auto size-3.5 text-text-subtle" aria-hidden />
                ) : null}
              </button>
            );
          })}
        </div>
        <div className="my-1 h-px bg-border-subtle" />
        <div className="flex flex-col gap-2 px-2 pb-2 pt-1.5">
          <span className="text-2xs font-semibold text-text-subtle">
            {t("activity.time.custom")}
          </span>
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-label text-text-muted">{t("activity.time.from")}</span>
              <Input
                value={draftFrom}
                onChange={(e) => setDraftFrom(e.target.value)}
                placeholder={t("common.dateTimeFormatHint")}
                aria-invalid={fromInvalid || undefined}
                className={cn("h-control-md", fromInvalid && "border-danger")}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-label text-text-muted">{t("activity.time.to")}</span>
              <Input
                value={draftTo}
                onChange={(e) => setDraftTo(e.target.value)}
                placeholder={t("activity.time.now")}
                aria-invalid={toInvalid || undefined}
                className={cn("h-control-md", toInvalid && "border-danger")}
              />
            </label>
          </div>
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={apply}
              disabled={fromInvalid || toInvalid || empty}
            >
              {t("activity.time.apply")}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
