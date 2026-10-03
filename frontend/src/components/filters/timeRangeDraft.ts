// src/components/filters/timeRangeDraft.ts — read a URL range value back into the custom-range panel's fields.
import type { DateRange } from "react-day-picker";

import { parseCustom, parseEnd } from "@/lib/filters/timeRangeValue";

export function draftFrom(value: string): { range?: DateRange; fromTime: string; toTime: string } {
  const custom = parseCustom(value);
  if (!custom) return { fromTime: "", toTime: "" };
  const from = parseEnd(custom.from);
  const to = custom.to === "now" ? undefined : parseEnd(custom.to);
  const time = (p?: { date: Date; dateOnly: boolean }) =>
    p && !p.dateOnly
      ? `${String(p.date.getHours()).padStart(2, "0")}:${String(p.date.getMinutes()).padStart(2, "0")}`
      : "";
  return {
    range: from ? { from: from.date, to: to?.date } : undefined,
    fromTime: time(from),
    toTime: time(to),
  };
}
