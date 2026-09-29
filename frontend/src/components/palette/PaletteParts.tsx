// src/components/palette/PaletteParts.tsx — the palette's small pieces: a row, a status line and a key hint.
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { PaletteItem } from "./paletteItems";

interface RowProps {
  item: PaletteItem;
  index: number;
  id: string;
  selected: boolean;
  onHover: () => void;
  onChoose: () => void;
}

/** One entry: its label, the name after a title, and its kind on the right. */
export function PaletteRow({ item, index, id, selected, onHover, onChoose }: RowProps) {
  return (
    <div
      id={id}
      role="option"
      aria-selected={selected}
      data-index={index}
      onMouseMove={onHover}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onChoose}
      className={cn(
        "mx-2 flex h-control-lg cursor-pointer items-center gap-2 rounded-item px-2.5",
        selected && "bg-surface-selected",
      )}
    >
      <span className="truncate font-label">{item.label}</span>
      {item.detail ? (
        <span className="truncate font-mono text-xs text-text-muted">{item.detail}</span>
      ) : null}
      {item.kindLabel ? (
        <span className="ml-auto shrink-0 text-xs text-text-muted">{item.kindLabel}</span>
      ) : null}
    </div>
  );
}

export function StatusLine({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "danger";
}) {
  return (
    <p
      role="status"
      className={cn(
        "mx-2 flex min-h-control-lg items-center px-2.5 text-xs",
        tone === "danger" ? "text-danger" : "text-text-muted",
      )}
    >
      {children}
    </p>
  );
}

export function Hint({ keys, label }: { keys: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <kbd className="rounded-xs bg-chip px-1 font-mono text-2xs text-text-muted">{keys}</kbd>
      {label}
    </span>
  );
}
