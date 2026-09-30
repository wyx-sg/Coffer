// src/components/custom-tools/WayCard.tsx — one of the two ways into a new group, as a choosable card.
import type { LucideIcon } from "lucide-react";

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
        "flex w-full items-start gap-3 rounded-xl border bg-surface-raised p-4 text-left transition-colors duration-fast",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        selected ? "border-text ring-1 ring-text" : "border-border hover:bg-surface-hover",
      )}
    >
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-sm font-semibold text-text">{title}</span>
        <span className="text-xs text-text-muted">{body}</span>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-text-muted">
          {points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </span>
    </button>
  );
}
