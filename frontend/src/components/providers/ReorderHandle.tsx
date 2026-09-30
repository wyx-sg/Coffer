// src/components/providers/ReorderHandle.tsx — the drag handle on a provider row (list order is fallback priority).
//
// Drag the row onto another to move it there; with the keyboard, focus the
// handle and press ↑ / ↓. Either way the whole new order is saved at once.
import { useTranslation } from "react-i18next";
import { GripVertical } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  name: string;
  disabled: boolean;
  onMove: (delta: -1 | 1) => void;
  onDragStart: () => void;
}

export function ReorderHandle({ name, disabled, onMove, onDragStart }: Props) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      draggable={!disabled}
      disabled={disabled}
      title={t("providers.list.dragToReorder")}
      aria-label={t("providers.list.reorderAria", { name })}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowUp" || e.key === "ArrowDown") {
          e.preventDefault();
          onMove(e.key === "ArrowUp" ? -1 : 1);
        }
      }}
      className={cn(
        "inline-flex h-7 w-4 shrink-0 cursor-grab items-center justify-center rounded text-text-subtle outline-none",
        "hover:text-text-muted focus-visible:ring-2 focus-visible:ring-focus-ring disabled:cursor-default disabled:opacity-40",
      )}
    >
      <GripVertical className="size-3.5" aria-hidden />
    </button>
  );
}

/** `uids` with the one at `from` moved to `to`. */
export function moved(uids: readonly string[], from: number, to: number): string[] {
  const next = [...uids];
  const [item] = next.splice(from, 1);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, item);
  return next;
}
