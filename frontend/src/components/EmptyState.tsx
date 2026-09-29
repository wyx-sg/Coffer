// src/components/EmptyState.tsx — the shared "nothing here yet" surface, and the inline error a list shows.
// A centred column: an icon tile, a title, an optional description and its
// first step — one primary action, optionally a secondary — so every list /
// not-found / zero-result screen reads the same (Foundations-Feedback "Empty
// state"). `tone="error"` is the list's inline error: the same layout with the
// tile toned danger, its actions a retry and a way to diagnose.
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  icon?: LucideIcon;
  title: string;
  description?: string;
  /** The first step — usually a primary Button (or Button asChild + Link). */
  action?: ReactNode;
  /** An optional second, secondary action beside the first. */
  secondaryAction?: ReactNode;
  /** "error" tones the tile danger for a list that failed to load. */
  tone?: "default" | "error";
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  tone = "default",
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex min-h-[200px] flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        className,
      )}
    >
      {Icon ? (
        <span
          data-tone={tone}
          className={cn(
            "inline-flex size-10 shrink-0 items-center justify-center rounded-lg border",
            tone === "error"
              ? "border-transparent bg-danger-soft text-danger"
              : "border-border-subtle bg-surface-sunken text-text-muted",
          )}
        >
          <Icon className="size-5" strokeWidth={1.75} aria-hidden />
        </span>
      ) : null}
      <div className="flex max-w-empty flex-col gap-1">
        <p className="text-md font-semibold text-text">{title}</p>
        {description ? (
          <p className="text-sm leading-normal text-text-muted">{description}</p>
        ) : null}
      </div>
      {action || secondaryAction ? (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      ) : null}
    </div>
  );
}
