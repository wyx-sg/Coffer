// frontend/src/pages/sync/SyncBanner.tsx
//
// The two shapes the Status tab's first line takes on the boards: a plain
// line (a 36px icon square, a 15/650 title and a muted subline) for a state
// that asks nothing of anyone, and the same inside a bordered card for one
// that does — a stopped round or a problem, with its actions under the text.
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

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
  testId?: string;
}

/** A state that asks nothing: icon, title, one line under it. */
export function SyncBannerLine({ icon, tone, title, children, testId = "sync-banner" }: Props) {
  return (
    <div className="flex items-center gap-4" data-testid={testId}>
      <IconSquare icon={icon} tone={tone} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-md font-bold text-text">{title}</p>
        {children ? <div className="text-sm text-text-subtle">{children}</div> : null}
      </div>
    </div>
  );
}

/** A state that asks for something: the same, boxed, with room for actions. */
export function SyncBannerCard({ icon, tone, title, children, testId = "sync-banner" }: Props) {
  return (
    <div
      className="flex items-start gap-4 rounded-xl border border-border bg-surface-raised p-4"
      data-testid={testId}
      role={tone === "err" || tone === "warn" ? "alert" : undefined}
    >
      <IconSquare icon={icon} tone={tone} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="text-sm font-bold text-text">{title}</p>
        {children}
      </div>
    </div>
  );
}
