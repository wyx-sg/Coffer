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

export { TIME_PRESETS };

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
 * Time-range filter: quick presets, a calendar for picking a custom
 * From–To window, and editable text fields for typing an exact date and
 * time. Styled to match the project's Select controls.
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

  const triggerLabel =
    timeRange === "custom"
      ? from && to
        ? `${from} → ${to}`
        : t("audit.timeRange.custom")
      : t(`audit.timeRange.${timeRange}`);

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
        <button
          type="button"
          className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        >
          <span className="flex items-center gap-2 truncate">
            <CalendarDays className="size-4 shrink-0 opacity-60" />
            {triggerLabel}
          </span>
          <ChevronDown className="size-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <div className="flex">
          <div className="flex w-32 flex-col gap-0.5 border-r border-border p-2">
            {TIME_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => {
                  onChange({ timeRange: p, from: "", to: "" });
                  setOpen(false);
                }}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                  timeRange === p
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-foreground/80 hover:bg-secondary",
                )}
              >
                {t(`audit.timeRange.${p}`)}
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
          <div className="flex w-56 flex-col gap-3 border-l border-border p-3">
            <div className="space-y-1">
              <Label htmlFor="tr-from">{t("audit.filter.from")}</Label>
              <Input
                id="tr-from"
                value={draftFrom}
                placeholder="2026-05-12 09:00:00"
                onChange={(e) => setDraftFrom(e.target.value)}
                className={cn(fromInvalid && "border-destructive")}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tr-to">{t("audit.filter.to")}</Label>
              <Input
                id="tr-to"
                value={draftTo}
                placeholder="2026-05-22 18:00:00"
                onChange={(e) => setDraftTo(e.target.value)}
                className={cn(toInvalid && "border-destructive")}
              />
            </div>
            <Button
              size="sm"
              onClick={applyCustom}
              disabled={fromInvalid || toInvalid || bothEmpty}
            >
              {t("audit.applyRange")}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
