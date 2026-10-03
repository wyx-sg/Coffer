// frontend/src/components/files/FileBrowserFrame.tsx
//
// The frame every file browser sits in (boards 2.1.40, 2.1.51, 2.1.52, 2.1.58):
// ONE bordered, rounded surface reaching the bottom of the window — the list or
// tree on the left (a fixed 288 by default), a hairline, the pane on the right.
// Not two cards and not a draggable split: the surface is the container and the
// hairline is the only divider.
import type { ReactNode } from "react";

import { useFillToBottom } from "@/components/filePane";
import { cn } from "@/lib/utils";

export function FileBrowserFrame({
  side,
  main,
  sideWidth = 288,
  className,
}: {
  side: ReactNode;
  main: ReactNode;
  /** The left column's width in px. */
  sideWidth?: number;
  className?: string;
}) {
  const fill = useFillToBottom();
  return (
    <div
      ref={fill.ref}
      style={fill.style}
      className={cn(
        "flex min-h-0 overflow-hidden rounded-xl border border-border bg-surface-raised",
        className,
      )}
    >
      <div
        // The width is a prop, not a token; the one inline style.
        style={{ width: sideWidth }}
        className="flex min-h-0 shrink-0 flex-col border-r border-border"
      >
        {side}
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">{main}</div>
    </div>
  );
}
