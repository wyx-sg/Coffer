// src/components/usage/QuotaMeter.tsx — one subscription window as a labelled meter: used %, bar, when it resets.
//
// The number is the vendor's own, never an estimate: a window with no current
// reading (none seen, or its reset has passed since) shows no percentage and
// an empty track. Tones come from the status vocabulary — 90% and up is a
// warning, 100% is "Limit reached" in danger; below that the fill stays muted.
import { useTranslation } from "react-i18next";

import type { QuotaWindow } from "@/lib/api/usage";
import { toneDotClass, toneTextClass, type Tone } from "@/lib/statusColors";
import { formatMoment, splitDuration } from "@/lib/usage/format";
import { cn } from "@/lib/utils";

const WARN_AT = 90;
const DAY_MS = 86_400_000;

interface Props {
  window: QuotaWindow;
  now: Date;
}

function toneFor(used: number): Tone | null {
  if (used >= 100) return "error";
  if (used >= WARN_AT) return "warn";
  return null;
}

export function QuotaMeter({ window: w, now }: Props) {
  const { t, i18n } = useTranslation();
  const used = w.used_percent;
  const tone = used === null ? null : toneFor(used);
  const limit = used !== null && used >= 100;

  const resetLine = (() => {
    if (!w.resets_at) return null;
    const left = new Date(w.resets_at).getTime() - now.getTime();
    if (left <= 0) return null;
    const when = formatMoment(w.resets_at, now, i18n.language);
    if (left >= DAY_MS && !limit) return t("usage.quota.resets", { when });
    const { days, hours, minutes } = splitDuration(left);
    const span = days
      ? t("usage.quota.in.dh", { days, hours })
      : hours
        ? t("usage.quota.in.hm", { hours, minutes: String(minutes).padStart(2, "0") })
        : t("usage.quota.in.m", { minutes });
    return t("usage.quota.resetsIn", { when, in: span });
  })();

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-baseline gap-2">
        <span className="truncate text-xs text-text-muted">{w.label}</span>
        <span
          className={cn(
            "ml-auto whitespace-nowrap text-xs font-label",
            tone ? toneTextClass(tone) : used === null ? "text-text-muted" : "text-text",
          )}
        >
          {used === null
            ? w.stale
              ? t("usage.quota.resetPassed")
              : t("usage.quota.noReading")
            : limit
              ? t("usage.quota.limitReached")
              : t("usage.quota.used", { percent: Math.round(used) })}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={w.label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={used === null ? undefined : Math.round(used)}
        className="h-1.5 overflow-hidden rounded-full bg-chip"
      >
        {used !== null ? (
          <div
            className={cn("h-full rounded-full", tone ? toneDotClass(tone) : "bg-text-muted")}
            // Theming bridge: the fill's width is the reading itself.
            style={{ width: `${Math.min(100, Math.max(0, used))}%` }}
          />
        ) : null}
      </div>
      {resetLine ? (
        <span className="whitespace-nowrap text-2xs text-text-muted">{resetLine}</span>
      ) : null}
    </div>
  );
}
