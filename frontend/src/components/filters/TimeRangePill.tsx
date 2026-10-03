// src/components/filters/TimeRangePill.tsx — the time-range filter: a pill whose popover lists presets and a custom range.
//
// Foundations 0.2.04. The pill reads the preset's name, or "Sep 29, 14:00 – now"
// for a custom range. "Custom range…" opens a calendar for the start and end
// day, optional HH:MM for each end (hidden when `dateOnly`), "To" defaulting to
// now, limited to MAX_RANGE_DAYS back. The value is the URL string from
// lib/filters/timeRangeValue.
import { useState } from "react";
import type { DateRange } from "react-day-picker";
import { CalendarDays, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  MAX_RANGE_DAYS,
  dayString,
  earliestDay,
  encodeCustom,
  formatCustom,
  isTime,
  makeEnd,
  parseCustom,
} from "@/lib/filters/timeRangeValue";
import { cn } from "@/lib/utils";
import { PILL_BUTTON, pillClass } from "./pillStyles";
import { FIELD, PresetList, TimeField } from "./TimeRangeParts";
import { draftFrom } from "./timeRangeDraft";

/** @ui-only One preset the page offers; `id` is what the URL carries. */
export interface TimeRangePreset {
  id: string;
  label: string;
}

interface Props {
  /** The URL string: a preset id or a custom range. */
  value: string;
  onChange: (value: string) => void;
  presets: readonly TimeRangePreset[];
  /** Days with no time-of-day part (Usage). */
  dateOnly?: boolean;
  /** How far back the calendar reaches. */
  maxDays?: number;
  /** Optional name shown before the value: "Time range: Last 24 h". */
  label?: string;
  className?: string;
}

export function TimeRangePill({
  value,
  onChange,
  presets,
  dateOnly = false,
  maxDays = MAX_RANGE_DAYS,
  label,
  className,
}: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"list" | "custom">("list");
  const [range, setRange] = useState<DateRange | undefined>();
  const [fromTime, setFromTime] = useState("");
  const [toTime, setToTime] = useState("");

  const custom = parseCustom(value);
  const preset = presets.find((p) => p.id === value);
  const shown = custom
    ? formatCustom(custom, lang, t("filters.timeRange.now"))
    : (preset?.label ?? value);

  const today = new Date();
  const earliest = earliestDay(today, maxDays);

  const fromBad = !dateOnly && fromTime !== "" && !isTime(fromTime);
  const toBad = !dateOnly && toTime !== "" && !isTime(toTime);
  const endBeforeStart = (() => {
    if (!range?.from || !range.to) return false;
    const a = new Date(range.from);
    const b = new Date(range.to);
    if (!dateOnly && isTime(fromTime)) a.setHours(+fromTime.slice(0, 2), +fromTime.slice(3));
    if (!dateOnly && isTime(toTime)) b.setHours(+toTime.slice(0, 2), +toTime.slice(3));
    else b.setHours(23, 59);
    return b < a;
  })();
  const canApply = Boolean(range?.from) && !fromBad && !toBad && !endBeforeStart;

  const openChange = (next: boolean) => {
    if (next) {
      const d = draftFrom(value);
      setRange(d.range);
      setFromTime(d.fromTime);
      setToTime(d.toTime);
      setView("list");
    }
    setOpen(next);
  };

  const choose = (id: string) => {
    onChange(id);
    setOpen(false);
  };

  const apply = () => {
    if (!range?.from) return;
    const from = makeEnd(range.from, dateOnly || !fromTime ? undefined : fromTime);
    const toDay = range.to ?? today;
    const toIsToday = dayString(toDay) === dayString(today);
    // No end typed on today = now, the board's default; otherwise whole-day or typed time.
    const to =
      !dateOnly && toIsToday && !toTime
        ? "now"
        : makeEnd(toDay, dateOnly || !toTime ? undefined : toTime);
    onChange(encodeCustom({ from, to }));
    setOpen(false);
  };

  const dayText = (d?: Date) =>
    d ? d.toLocaleDateString(lang, { month: "short", day: "numeric", year: "numeric" }) : "—";

  return (
    <Popover open={open} onOpenChange={openChange}>
      <div className={cn(pillClass(Boolean(custom), open), className)}>
        <PopoverTrigger asChild>
          <button type="button" className={PILL_BUTTON}>
            <CalendarDays className="size-3.5 text-text-subtle" aria-hidden />
            {label ? <span className="shrink-0">{label}:</span> : null}
            <span className="truncate font-[550] text-text">{shown}</span>
            <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
          </button>
        </PopoverTrigger>
      </div>
      <PopoverContent
        className={cn(
          "rounded-[10px] border border-border p-1",
          view === "custom" ? "w-auto max-w-[calc(100vw-2rem)] p-3" : "w-[232px]",
        )}
        align="start"
      >
        {view === "list" ? (
          <PresetList
            label={label ?? t("filters.timeRange.label")}
            presets={presets}
            value={value}
            custom={Boolean(custom)}
            onChoose={choose}
            onCustom={() => setView("custom")}
          />
        ) : (
          <div className="flex flex-col gap-2.5" aria-label={t("filters.timeRange.customHeading")}>
            <Calendar
              mode="range"
              selected={range}
              onSelect={setRange}
              defaultMonth={range?.from ?? today}
              disabled={{ before: earliest, after: today }}
              startMonth={earliest}
              endMonth={today}
              weekStartsOn={1}
            />
            <div className="flex flex-col gap-1.5">
              {(
                [
                  [
                    "from",
                    t("filters.timeRange.from"),
                    range?.from,
                    fromTime,
                    setFromTime,
                    fromBad,
                    "14:00",
                  ],
                  [
                    "to",
                    t("filters.timeRange.to"),
                    range?.to,
                    toTime,
                    setToTime,
                    toBad,
                    t("filters.timeRange.now"),
                  ],
                ] as const
              ).map(([key, name, day, time, set, bad, placeholder]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-9 shrink-0 text-xs text-text-muted">{name}</span>
                  <span className={cn(FIELD, "flex-1")}>
                    {key === "to" && !day && range?.from
                      ? t("filters.timeRange.now")
                      : dayText(day)}
                  </span>
                  {dateOnly ? null : (
                    <TimeField
                      value={time}
                      onChange={set}
                      invalid={bad}
                      placeholder={placeholder}
                      name={`${name} HH:MM`}
                    />
                  )}
                </div>
              ))}
            </div>
            <p
              className={cn(
                "text-2xs",
                fromBad || toBad || endBeforeStart ? "text-danger" : "text-text-subtle",
              )}
            >
              {fromBad || toBad
                ? t("filters.timeRange.invalidTime")
                : endBeforeStart
                  ? t("filters.timeRange.endBeforeStart")
                  : t(dateOnly ? "filters.timeRange.hintDate" : "filters.timeRange.hint", {
                      days: maxDays,
                    })}
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                {t("filters.timeRange.cancel")}
              </Button>
              <Button size="sm" onClick={apply} disabled={!canApply}>
                {t("filters.timeRange.apply")}
              </Button>
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
