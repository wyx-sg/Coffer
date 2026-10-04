// frontend/src/components/files/FileBrowserFrame.tsx
//
// The frame every file browser sits in (boards 2.1.40, 2.1.51, 2.1.52, 2.1.58;
// canvas 4.3.01): ONE bordered, rounded surface reaching the bottom of the
// window — the list or tree on the left (a fixed 288 by default), a hairline,
// the pane on the right. Not two cards: the surface is the container and the
// hairline is the only divider.
//
// `resizable` makes the hairline a draggable divider (a skill folder's Files
// card): the tree keeps its width per `storageKey`, may shrink to
// `listMinWidth`, the pane keeps `detailMinWidth`, and below both the frame
// scrolls sideways rather than squeezing the open file.
import type { ReactNode } from "react";

import { useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { cn } from "@/lib/utils";

interface Resizable {
  /** Names the remembered width (`coffer.split.<storageKey>`). */
  storageKey: string;
  /** The divider's accessible name. */
  label: string;
  listMinWidth: number;
  detailMinWidth: number;
}

export function FileBrowserFrame({
  side,
  main,
  sideWidth = 288,
  resizable,
  className,
}: {
  side: ReactNode;
  main: ReactNode;
  /** The left column's width in px (the starting width when resizable). */
  sideWidth?: number;
  resizable?: Resizable;
  className?: string;
}) {
  const fill = useFillToBottom();
  const frame = "flex min-h-0 rounded-xl border border-border bg-surface-raised";
  if (resizable) {
    return (
      <div
        ref={fill.ref}
        style={fill.style}
        className={cn(frame, "overflow-x-auto overflow-y-hidden", className)}
      >
        <SplitView
          storageKey={resizable.storageKey}
          label={resizable.label}
          defaultListWidth={sideWidth}
          // The two minimums plus the divider: narrower than that, the frame scrolls.
          className="min-h-0 min-w-[504px] flex-1"
          listMinWidth={resizable.listMinWidth}
          detailMinWidth={resizable.detailMinWidth}
          list={<div className="flex min-h-0 flex-1 flex-col">{side}</div>}
          detail={<div className="flex min-h-0 min-w-0 flex-1 flex-col">{main}</div>}
        />
      </div>
    );
  }
  return (
    <div ref={fill.ref} style={fill.style} className={cn(frame, "overflow-hidden", className)}>
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
