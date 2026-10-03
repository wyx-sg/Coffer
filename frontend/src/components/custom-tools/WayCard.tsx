// src/components/custom-tools/WayCard.tsx — one of the two ways into a new group, as a choosable card.
import { ChevronRight, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  icon: LucideIcon;
  title: string;
  body: string;
  /** Short facts under the body, one per line. */
  points: string[];
  selected?: boolean;
  onSelect: () => void;
  /** `radio` inside a choice; `button` where the card acts at once. */
  role?: "radio" | "button";
}

export function WayCard({
  icon: Icon,
  title,
  body,
  points,
  selected = false,
  onSelect,
  role = "radio",
}: Props) {
  return (
    <button
      type="button"
      role={role}
      aria-checked={role === "radio" ? selected : undefined}
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-3 rounded-xl border bg-surface-raised p-3.5 text-left transition-colors duration-fast",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        selected ? "border-accent ring-1 ring-accent" : "border-border hover:bg-surface-hover",
      )}
    >
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-sm font-semibold text-text">{title}</span>
        <span className="text-xs text-text-muted">{body}</span>
        <ul
          className={cn(
            "mt-1 space-y-0.5 text-xs text-text-muted",
            role === "radio" ? "list-disc pl-4" : "list-none",
          )}
        >
          {points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </span>
      {role === "button" ? (
        <ChevronRight className="mt-2 size-3.5 shrink-0 text-text-subtle" aria-hidden />
      ) : null}
    </button>
  );
}
