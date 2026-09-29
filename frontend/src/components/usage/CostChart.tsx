// src/components/usage/CostChart.tsx — "Cost per day": one accent bar per local day of the range, today's lighter.
//
// A single series, so no legend box beyond "Today, so far" (today's bar is
// partial). Bars sit on the baseline with rounded tops and a 2px gap; each one
// is focusable and names its day and cost in a tooltip. Only a sample of days
// is labelled on the axis so a 30-day range does not collide. The By day tab
// below is the table view of the same numbers.
import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { UsageSummary } from "@/lib/api/usage";
import { formatCost, formatDay, niceTicks } from "@/lib/usage/format";
import { daysBetween, localDay, parseDay } from "@/lib/usage/range";
import { cn } from "@/lib/utils";

const MAX_AXIS_LABELS = 7;

export function CostChart({ byDay }: { byDay: UsageSummary }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const today = localDay(new Date());
  const cost = new Map(byDay.rows.map((r) => [r.day ?? r.key, r.totals.estimated_cost_usd]));
  const days = daysBetween(byDay.start, byDay.end).map((day) => ({
    day,
    cost: cost.get(day) ?? 0,
    today: day === today,
  }));
  const { step, ticks } = niceTicks(Math.max(0, ...days.map((d) => d.cost)));
  const top = ticks[ticks.length - 1];
  const digits = step >= 1 ? 0 : 2;
  const every = Math.ceil(days.length / MAX_AXIS_LABELS);
  const labelled = (i: number) => days.length <= MAX_AXIS_LABELS || i % every === 0;
  const dayName = (d: (typeof days)[number], style: "short" | "long") =>
    d.today ? t("usage.chart.todayShort") : formatDay(parseDay(d.day), lang, style);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-text-muted">{t("usage.chart.title")}</span>
        {days.some((d) => d.today) ? (
          <span className="ml-auto inline-flex items-center gap-1.5 text-2xs text-text-muted">
            <span aria-hidden className="size-2 rounded-xs bg-accent/55" />
            {t("usage.chart.today")}
          </span>
        ) : null}
      </div>
      <figure aria-label={t("usage.chart.title")} className="m-0 flex min-w-0 flex-col gap-1.5">
        <div className="flex gap-2.5">
          <div className="relative h-28 w-9 shrink-0" aria-hidden>
            {ticks.map((v) => (
              <span
                key={v}
                className="absolute right-0 translate-y-1/2 text-2xs text-text-muted"
                // Theming bridge: a tick's position is its value on the axis.
                style={{ bottom: `${(v / top) * 100}%` }}
              >
                {formatCost(v, lang, digits)}
              </span>
            ))}
          </div>
          <div className="relative h-28 flex-1">
            {ticks.map((v) => (
              <div
                key={v}
                aria-hidden
                className={cn(
                  "absolute inset-x-0 border-t",
                  v === 0 ? "border-border" : "border-dashed border-border-subtle",
                )}
                style={{ bottom: `${(v / top) * 100}%` }}
              />
            ))}
            <div className="absolute inset-0 flex items-end gap-0.5">
              {days.map((d) => {
                const name = d.today
                  ? t("usage.chart.todayBar", { cost: formatCost(d.cost, lang) })
                  : t("usage.chart.bar", {
                      day: formatDay(parseDay(d.day), lang, "long"),
                      cost: formatCost(d.cost, lang),
                    });
                return (
                  <Tooltip key={d.day}>
                    <TooltipTrigger asChild>
                      <div
                        role="img"
                        tabIndex={0}
                        aria-label={name}
                        className="flex h-full min-w-0 flex-1 items-end justify-center rounded-xs outline-none hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring"
                      >
                        <div
                          className={cn(
                            "w-full max-w-11 rounded-t-xs",
                            d.today ? "bg-accent/55" : "bg-accent",
                          )}
                          // Theming bridge: the bar's height is the day's cost.
                          style={{ height: `${(d.cost / top) * 100}%` }}
                        />
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>{name}</TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        </div>
        <div className="flex gap-0.5 pl-[46px]" aria-hidden>
          {days.map((d, i) => (
            <span
              key={d.day}
              className="min-w-0 flex-1 overflow-visible whitespace-nowrap text-center text-2xs text-text-muted"
            >
              {labelled(i) ? dayName(d, days.length <= MAX_AXIS_LABELS ? "short" : "long") : ""}
            </span>
          ))}
        </div>
      </figure>
    </div>
  );
}
