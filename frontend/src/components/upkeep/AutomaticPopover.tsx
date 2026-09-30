// frontend/src/components/upkeep/AutomaticPopover.tsx
//
// The "Automatic · hourly" pill in the Knowledge and Memory page headers and
// the popover it opens (designs 5.1.24 and 5.2.11). Automatic upkeep lives on
// the page it upkeeps, not in Settings: this is the frame both pages share —
// a switch with its one-line explanation, an interval, any page-specific rows,
// and a footer with when the pass last ran and runs next, plus an optional
// action. Each change saves as it is made; there is no Save button.
import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { UpkeepSetting } from "@/lib/api/internalEngine";
import { cn } from "@/lib/utils";

/** The intervals offered, in seconds. */
const INTERVAL_CHOICES = [
  15 * 60,
  30 * 60,
  60 * 60,
  3 * 60 * 60,
  6 * 60 * 60,
  12 * 60 * 60,
  86400,
];

/** The interval select's value for "this pass's own default". */
const DEFAULT_VALUE = "default";

type Translate = ReturnType<typeof useTranslation>["t"];

/** "1 hour", "30 minutes", "1 day" — the interval as the picker names it. */
function intervalName(t: Translate, seconds: number): string {
  if (seconds % 86400 === 0) return t("upkeep.interval.days", { count: seconds / 86400 });
  if (seconds % 3600 === 0) return t("upkeep.interval.hours", { count: seconds / 3600 });
  return t("upkeep.interval.minutes", { count: Math.round(seconds / 60) });
}

/** "hourly", "every 6 h", "off" — the pill's short form. */
function pillState(t: Translate, setting: UpkeepSetting): string {
  if (!setting.enabled) return t("upkeep.pill.off");
  const seconds = setting.interval_s ?? setting.default_interval_s;
  if (seconds === 3600) return t("upkeep.pill.hourly");
  if (seconds === 86400) return t("upkeep.pill.daily");
  return t("upkeep.pill.every", { interval: intervalName(t, seconds) });
}

/** "Last pass 2 h ago · next in 58 min" — each half left out when unknown. */
export function clockLine(
  t: Translate,
  language: string,
  setting: UpkeepSetting,
  lastKey: string,
  neverKey: string,
): string {
  const last = setting.last_pass_at
    ? t(lastKey, { when: formatRelativeTime(setting.last_pass_at, language) })
    : t(neverKey);
  if (!setting.enabled || !setting.next_pass_at) return last;
  return `${last} · ${t("upkeep.next", { when: formatRelativeTime(setting.next_pass_at, language) })}`;
}

interface Props {
  /** Accessible name and heading of the popover, e.g. "Automatic curation". */
  title: string;
  /** One line under the heading saying what the pass does. */
  description: string;
  /** The setting that drives the switch, the interval and the pill. */
  setting: UpkeepSetting;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  /** A number of seconds, or `null` for the pass's own default. */
  onInterval: (seconds: number | null) => void;
  /** Overrides the pill's state word and dot, e.g. for a fault. */
  pill?: { state: string; tone: "ok" | "off" | "err" };
  /** Page-specific rows between the interval and the footer. */
  children?: ReactNode;
  /** The footer's left half: when the pass last ran and runs next. */
  clock: string;
  /** The footer's right half, e.g. Curate now. */
  action?: ReactNode;
  testId?: string;
}

export function AutomaticPopover({
  title,
  description,
  setting,
  busy,
  onToggle,
  onInterval,
  children,
  clock,
  action,
  testId,
  pill,
}: Props) {
  const { t } = useTranslation();
  const seconds = setting.interval_s ?? setting.default_interval_s;
  const choices = INTERVAL_CHOICES.includes(seconds)
    ? INTERVAL_CHOICES
    : [...INTERVAL_CHOICES, seconds].sort((a, b) => a - b);
  const tone = pill?.tone ?? (setting.enabled ? "ok" : "off");

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid={testId}
          className="inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-border bg-surface px-2 text-xs font-medium text-text-muted hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span
            aria-hidden
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              tone === "ok" ? "bg-status-ok" : tone === "err" ? "bg-status-err" : "bg-text-subtle",
            )}
          />
          {t("upkeep.pill.label", { state: pill?.state ?? pillState(t, setting) })}
          <ChevronDown aria-hidden className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        aria-label={title}
        className="flex w-[330px] flex-col gap-3.5 px-4 py-3.5 text-sm text-text"
      >
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2.5">
            <span className="grow font-semibold">{title}</span>
            <Switch
              checked={setting.enabled}
              onCheckedChange={onToggle}
              disabled={busy}
              aria-label={title}
            />
          </div>
          <span className="text-xs leading-snug text-text-muted">{description}</span>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="grow">{t("upkeep.every")}</span>
          <Select
            value={setting.interval_s === null ? DEFAULT_VALUE : String(setting.interval_s)}
            onValueChange={(v) => onInterval(v === DEFAULT_VALUE ? null : Number(v))}
            disabled={busy || !setting.enabled}
          >
            <SelectTrigger className="h-7 w-auto gap-2 text-xs" aria-label={t("upkeep.every")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_VALUE}>
                {t("upkeep.interval.default", {
                  interval: intervalName(t, setting.default_interval_s),
                })}
              </SelectItem>
              {choices.map((s) => (
                <SelectItem key={s} value={String(s)}>
                  {intervalName(t, s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {children}
        <div className="flex items-center gap-2 border-t border-border-subtle pt-3">
          <span className="text-xs text-text-subtle">{clock}</span>
          {action ? <span className="ml-auto">{action}</span> : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
