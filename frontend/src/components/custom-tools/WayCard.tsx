// src/components/custom-tools/WayCard.tsx — one of the two ways into a custom tool, as a choosable card.
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  icon: LucideIcon;
  title: string;
  body: string;
  /** Short facts under the body, one per line. */
  points: string[];
  selected?: boolean;
  disabled?: boolean;
  /** A line saying why the card cannot be chosen now. */
  disabledNote?: string;
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
  disabled = false,
  disabledNote,
  onSelect,
  role = "radio",
}: Props) {
  return (
    <button
      type="button"
      role={role}
      aria-checked={role === "radio" ? selected : undefined}
      aria-disabled={disabled || undefined}
      onClick={() => {
        if (!disabled) onSelect();
      }}
      className={cn(
        "flex w-full flex-col gap-2 rounded-xl border bg-surface-raised p-4 text-left transition-colors duration-fast",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
        selected ? "border-accent bg-accent-soft" : "border-border hover:bg-surface-hover",
        disabled && "cursor-not-allowed opacity-disabled hover:bg-surface-raised",
      )}
    >
      <span className="flex items-center gap-2 text-sm font-semibold text-text">
        <Icon className="size-4 text-text-subtle" aria-hidden />
        {title}
      </span>
      <span className="text-xs text-text-muted">{body}</span>
      <ul className="space-y-0.5 text-xs text-text-muted">
        {points.map((point) => (
          <li key={point}>· {point}</li>
        ))}
      </ul>
      {disabled && disabledNote ? (
        <span className="text-xs text-text-subtle">{disabledNote}</span>
      ) : null}
    </button>
  );
}
