// frontend/src/components/TimeRangePicker.tsx
// Time-range filter shared by the Activity tabs and the MCP invocations table:
// quick presets, a calendar for picking a custom From–To window, and editable
// text fields for typing an exact date and time. Its copy lives under the
// `timeRange.*` i18n namespace, which nothing else consumes.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarDays, ChevronDown } from "lucide-react";
import type { DateRange } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn, formatLocalDateTime } from "@/lib/utils";
import { TIME_PRESETS, parseLocalDate } from "@/lib/timeRange";

export interface TimeRangeValue {
  /** A TIME_PRESETS key, or "custom" when from/to are set. */
  timeRange: string;
  /** "YYYY-MM-DD HH:mm:ss" local datetimes — used only when timeRange === "custom". */
  from: string;
  to: string;
}

interface Props extends TimeRangeValue {
  onChange: (next: TimeRangeValue) => void;
}

const fmt = formatLocalDateTime;
const parse = parseLocalDate;

/**
 * Foundations-Pickers "Time range": the trigger is a md secondary button — a
 * 14px calendar icon, the range as its label, a 13px chevron — and the presets
 * are menu items. The panel is three columns
 * (presets · calendar · typed bounds) from the `sm` breakpoint and stacks to
 * one column below it, so it never forces the page to scroll sideways.
 */
export function TimeRangePicker({ timeRange, from, to, onChange }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draftFrom, setDraftFrom] = useState(from);
  const [draftTo, setDraftTo] = useState(to);

  const fromDate = parse(draftFrom);
  const toDate = parse(draftTo);
  const fromInvalid = draftFrom.trim() !== "" && !fromDate;
  const toInvalid = draftTo.trim() !== "" && !toDate;
  const formatHint = t("common.dateTimeFormatHint");

  const triggerLabel =
    timeRange === "custom"
      ? from && to
        ? `${from} → ${to}`
        : t("timeRange.custom")
      : t(`timeRange.${timeRange}`);

  function handleOpenChange(next: boolean) {
    // Re-seed the draft from the committed value whenever we open.
    if (next) {
      setDraftFrom(from);
      setDraftTo(to);
    }
    setOpen(next);
  }

  function pickRange(range: DateRange | undefined) {
    // The calendar sets the date; keep any time the user already typed.
    if (range?.from) {
      const d = new Date(range.from);
      const prev = parse(draftFrom);
      d.setHours(prev?.getHours() ?? 0, prev?.getMinutes() ?? 0, prev?.getSeconds() ?? 0, 0);
      setDraftFrom(fmt(d));
    } else {
      setDraftFrom("");
    }
    if (range?.to) {
      const d = new Date(range.to);
      const prev = parse(draftTo);
      d.setHours(prev?.getHours() ?? 23, prev?.getMinutes() ?? 59, prev?.getSeconds() ?? 59, 0);
      setDraftTo(fmt(d));
    } else {
      setDraftTo("");
    }
  }

  const bothEmpty = draftFrom.trim() === "" && draftTo.trim() === "";

  function applyCustom() {
    // Committing a "custom" range with neither bound set would silently
    // degrade to an all-time query while the trigger still reads "Custom".
    // Treat empty input as clearing back to the "all" preset instead.
    if (bothEmpty) {
      onChange({ timeRange: "all", from: "", to: "" });
    } else {
      onChange({ timeRange: "custom", from: draftFrom.trim(), to: draftTo.trim() });
    }
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" className="min-w-[10rem] justify-between">
          <span className="flex min-w-0 items-center gap-1.5">
            <CalendarDays aria-hidden className="text-text-subtle" />
            <span className="truncate">{triggerLabel}</span>
          </span>
          <ChevronDown aria-hidden className="text-text-subtle" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto max-w-[calc(100vw-2rem)] p-0" align="start">
        <div className="grid grid-cols-1 sm:grid-cols-[auto_auto_auto]">
          <div className="flex flex-col gap-px border-b border-border-subtle p-1 sm:border-b-0 sm:border-r">
            {TIME_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => {
                  onChange({ timeRange: p, from: "", to: "" });
                  setOpen(false);
                }}
                className={cn(
                  "flex h-control-md items-center rounded-item px-2 text-left text-sm text-text outline-none transition-colors duration-fast",
                  "focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
                  timeRange === p ? "bg-surface-selected font-label" : "hover:bg-surface-hover",
                )}
              >
                {t(`timeRange.${p}`)}
              </button>
            ))}
          </div>
          <div className="p-2">
            <Calendar
              mode="range"
              numberOfMonths={1}
              defaultMonth={fromDate}
              selected={fromDate ? { from: fromDate, to: toDate } : undefined}
              onSelect={pickRange}
            />
          </div>
          <div className="flex flex-col gap-3 border-t border-border-subtle p-3 sm:w-56 sm:border-l sm:border-t-0">
            <div className="space-y-1.5">
              <Label htmlFor="tr-from">{t("timeRange.from")}</Label>
              <Input
                id="tr-from"
                value={draftFrom}
                placeholder={formatHint}
                onChange={(e) => setDraftFrom(e.target.value)}
                aria-invalid={fromInvalid || undefined}
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tr-to">{t("timeRange.to")}</Label>
              <Input
                id="tr-to"
                value={draftTo}
                placeholder={formatHint}
                onChange={(e) => setDraftTo(e.target.value)}
                aria-invalid={toInvalid || undefined}
                className="font-mono text-xs"
              />
            </div>
            <p className="text-xs text-text-subtle">{formatHint}</p>
            <Button
              size="sm"
              onClick={applyCustom}
              disabled={fromInvalid || toInvalid || bothEmpty}
            >
              {t("timeRange.apply")}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
