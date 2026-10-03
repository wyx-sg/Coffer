// src/components/LoadErrorRow.tsx — a region that failed to load, said in one bordered row (Foundations 0.3.02 "Load error").
//
// Inside the region that failed — the header and filters around it stay: an
// icon, a 13/600 title, one sentence of reason, and on the right the region's
// own next steps (Retry as a small secondary button, a diagnose link, or a
// hand-off). Not a banner, not a centred empty state, not a primary Retry.
//
// `tone="neutral"` is the same row for a state that is not a failure of this
// region — "History needs git": an info icon and a grey reason.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CircleAlert, Info, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  /** One sentence. Pass `error` instead to show the daemon's readable message. */
  reason?: ReactNode;
  error?: unknown;
  onRetry?: () => void;
  /** Further actions after Retry: a diagnose link, Check again, a hand-off. */
  actions?: ReactNode;
  tone?: "danger" | "neutral";
  className?: string;
}

export function LoadErrorRow({
  title,
  reason,
  error,
  onRetry,
  actions,
  tone = "danger",
  className,
}: Props) {
  const { t } = useTranslation();
  const Icon = tone === "danger" ? CircleAlert : Info;
  const text = reason ?? (error !== undefined ? translateApiError(t, error) : null);
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border px-3.5 py-3",
        className,
      )}
    >
      <Icon
        aria-hidden
        className={cn(
          "size-[15px] shrink-0 stroke-[1.75]",
          tone === "danger" ? "text-danger" : "text-text-muted",
        )}
      />
      <div className="flex min-w-0 flex-1 basis-60 flex-col gap-0.5">
        <span className="text-sm font-semibold text-text">{title}</span>
        {text ? (
          <span className={cn("text-xs", tone === "danger" ? "text-danger" : "text-text-muted")}>
            {text}
          </span>
        ) : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {actions}
        {onRetry ? (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            <RotateCcw aria-hidden /> {t("common.retry")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
