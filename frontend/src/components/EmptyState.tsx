// src/components/EmptyState.tsx — the shared "nothing here yet" surface, and the inline error a list shows.
// A centred column: an icon tile, a title, an optional description and its
// first step — one primary action, optionally a secondary — so every list /
// not-found / zero-result screen reads the same (Foundations-Feedback "Empty
// state"). `tone="error"` is the list's inline error: the same layout with the
// tile toned danger, its actions a retry and a way to diagnose, and `detail`
// the failed request in mono under them.
//
// `size="compact"` is the same states inside a narrow list pane (Shell boards):
// a filter that matched nothing is a centred title 13/550, a help line and one
// small action, with no tile ("No server matches “q”" + Clear filter); an
// error is a danger-soft block, left-aligned, its icon beside the title
// (Shell-ListError). Detail panes keep the default size. `size="page"` is a
// detail page whose object is gone (Shell-DetailNotFound): a 44 tile, an
// 18/650 title, 420 wide, and `children` — the facts that explain it, as
// key-value rows — above the actions.
import { AlertTriangle, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  icon?: LucideIcon;
  title: string;
  /** One short paragraph; a node when part of it is set in mono (an id). */
  description?: ReactNode;
  /** The first step — usually a primary Button (or Button asChild + Link). */
  action?: ReactNode;
  /** An optional second, secondary action beside the first. */
  secondaryAction?: ReactNode;
  /** "error" tones the tile danger for a list that failed to load. */
  tone?: "default" | "error";
  /** A pasteable line under the actions — for an error, the failed request
   *  ("GET /api/v1/… · 500 · trace …"), set in mono. */
  detail?: string;
  /** "compact" for a narrow list pane: no tile; an error becomes a banner
   *  block. "page" for a detail page whose object no longer exists. */
  size?: "default" | "compact" | "page";
  /** Content between the text and the actions (`page`: key-value rows). */
  children?: ReactNode;
  className?: string;
}

function Actions({
  action,
  secondary,
  start,
}: {
  action?: ReactNode;
  secondary?: ReactNode;
  /** Left-aligned, for the compact error block. */
  start?: boolean;
}) {
  if (!action && !secondary) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-2", !start && "justify-center")}>
      {action}
      {secondary}
    </div>
  );
}

const DETAIL = "break-all font-mono text-2xs text-text-subtle";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  tone = "default",
  detail,
  size = "default",
  children,
  className,
}: Props) {
  if (size === "compact" && tone === "error") {
    const Mark = Icon ?? AlertTriangle;
    return (
      <div
        role="alert"
        data-tone="error"
        className={cn("flex flex-col items-start gap-2 rounded-lg bg-danger-soft p-3.5", className)}
      >
        <p className="flex items-center gap-2 text-sm font-semibold text-text">
          <Mark className="size-[15px] shrink-0 text-danger" strokeWidth={1.75} aria-hidden />
          {title}
        </p>
        {description ? (
          <p className="text-xs leading-[1.45] text-text-muted">{description}</p>
        ) : null}
        {children}
        <Actions action={action} secondary={secondaryAction} start />
        {detail ? <p className={DETAIL}>{detail}</p> : null}
      </div>
    );
  }

  if (size === "compact") {
    return (
      <div className={cn("flex flex-col items-center gap-2 px-4 py-9 text-center", className)}>
        <p className="text-sm font-label text-text">{title}</p>
        {description ? <p className="text-xs text-text-muted">{description}</p> : null}
        {children}
        <Actions action={action} secondary={secondaryAction} />
        {detail ? <p className={DETAIL}>{detail}</p> : null}
      </div>
    );
  }

  const page = size === "page";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        page
          ? "mx-auto w-full max-w-[420px] gap-[18px] px-4 py-8"
          : "min-h-[200px] gap-3 px-6 py-12",
        className,
      )}
    >
      {Icon ? (
        <span
          data-tone={tone}
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-lg border",
            page ? "size-11" : "size-10",
            tone === "error"
              ? "border-transparent bg-danger-soft text-danger"
              : "border-border-subtle bg-surface-sunken text-text-muted",
          )}
        >
          <Icon className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
      ) : null}
      <div className={cn("flex flex-col", page ? "gap-1.5" : "max-w-empty gap-1")}>
        {page ? (
          <h1 className="text-lg font-bold text-text">{title}</h1>
        ) : (
          <p className="text-md font-semibold text-text">{title}</p>
        )}
        {description ? (
          <p className="text-sm leading-normal text-text-muted">{description}</p>
        ) : null}
      </div>
      {children ? <div className="w-full text-left">{children}</div> : null}
      <Actions action={action} secondary={secondaryAction} />
      {detail ? <p className={cn(DETAIL, "max-w-empty")}>{detail}</p> : null}
    </div>
  );
}
