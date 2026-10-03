// frontend/src/pages/sync/SyncBanner.tsx
//
// The two shapes the Status tab's first line takes on the boards: a plain
// line (a 36px icon square, a 15/650 title and a muted subline) for a state
// that asks nothing of anyone, and a tinted card for one that does — a
// stopped round or a problem, with its actions under the text and an × (Ignore).
import { X, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { PillTone } from "./syncPageState";

const SQUARE: Record<PillTone, string> = {
  ok: "bg-success-soft text-success",
  info: "bg-accent-soft text-accent-text",
  warn: "bg-warning-soft text-warning",
  err: "bg-danger-soft text-danger",
  off: "bg-neutral-soft text-text-muted",
};

function IconSquare({ icon: Icon, tone }: { icon: LucideIcon; tone: PillTone }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-border-subtle",
        SQUARE[tone],
      )}
    >
      <Icon className="size-4" />
    </span>
  );
}

interface Props {
  icon: LucideIcon;
  tone: PillTone;
  title: ReactNode;
  children?: ReactNode;
  /** A last grey line under the text (the areas line on the Status boards). */
  footnote?: ReactNode;
  testId?: string;
}

/** A state that asks nothing: icon, title, one line under it. */
export function SyncBannerLine({
  icon,
  tone,
  title,
  children,
  footnote,
  testId = "sync-banner",
}: Props) {
  return (
    <div className="flex items-start gap-3.5" data-testid={testId}>
      <IconSquare icon={icon} tone={tone} />
      <div className="flex min-w-0 flex-col gap-[3px]">
        <p className="text-md font-semibold text-text">{title}</p>
        {children ? <div className="text-sm text-text-subtle">{children}</div> : null}
        {footnote}
      </div>
    </div>
  );
}

const CARD: Record<PillTone, string> = {
  err: "border-danger/30 bg-danger-soft",
  warn: "border-warning/30 bg-warning-soft",
  ok: "border-border bg-surface-raised",
  info: "border-border bg-surface-raised",
  off: "border-border bg-surface-raised",
};

const ICON: Record<PillTone, string> = {
  err: "text-danger",
  warn: "text-warning",
  ok: "text-success",
  info: "text-accent-text",
  off: "text-text-muted",
};

/** A state that asks for something: a tinted card (principle 16) with room for
 *  actions, and an × that is Ignore (principle 19) when `onIgnore` is given. */
export function SyncBannerCard({
  icon: Icon,
  tone,
  title,
  children,
  onIgnore,
  testId = "sync-banner",
}: Props & { onIgnore?: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      className={cn("flex items-start gap-3 rounded-xl border px-3.5 py-3", CARD[tone])}
      data-testid={testId}
      role={tone === "err" || tone === "warn" ? "alert" : undefined}
    >
      <Icon className={cn("mt-px size-4 shrink-0", ICON[tone])} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-sm font-semibold text-text">{title}</p>
        {children}
      </div>
      {onIgnore ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="-my-1 -mr-1.5"
              aria-label={t("sync.problem.ignore")}
              onClick={onIgnore}
            >
              <X aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("sync.problem.ignore")}</TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}
