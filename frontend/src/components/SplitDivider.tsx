// src/components/SplitDivider.tsx — the draggable, keyboard-operable divider between two panes.
//
// Board 1.1.21: a 1px hairline in the border colour with an invisible 12px hit
// area centred on it; on hover and while dragging a 2px accent line and the
// col-resize cursor; on keyboard focus the accent line plus the focus ring.
// It is the divider only — the caller owns the width (usually through
// `useResizableWidth`) and places it between any two panes, so the app
// sidebar uses it on its own and `SplitView` uses it for list/detail.
//
// With `onPreview` a drag is cheap: every pointer move reports the clamped
// width there (the caller moves its pane directly, no React render) and
// `onChange` fires once, with the final width, when the drag ends. Without it
// `onChange` fires on every move. Keyboard steps always use `onChange`.
//
// Behaviour: drag with pointer events (captured, so the drag follows the
// pointer outside the line); ← / → move by `KEYBOARD_STEP`, Home / End jump to
// the bounds; double-click resets. Every value it emits is clamped.
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { clampWidth } from "@/lib/hooks/useResizableWidth";
import { cn } from "@/lib/utils";

/** How far one ← / → press moves the divider (px). */
export const KEYBOARD_STEP = 16;

// Put on <body> while dragging so no text is selected and the cursor stays
// col-resize wherever the pointer wanders.
const DRAGGING_BODY_CLASSES = ["select-none", "cursor-col-resize"];

export interface SplitDividerProps {
  /** Current width (px) of the pane the divider resizes. */
  value: number;
  min: number;
  /** Upper bound (px); may be `Infinity` when the caller has no measurement yet. */
  max: number;
  onChange: (next: number) => void;
  /** Optional: receives the width during a pointer drag instead of `onChange`,
   *  which then fires once at the end of the drag. */
  onPreview?: (next: number) => void;
  /** Double-click: restore the split's default width. */
  onReset: () => void;
  /** Accessible name — what the divider resizes, e.g. "Resize the list". */
  label: string;
  className?: string;
}

export function SplitDivider({
  value,
  min,
  max,
  onChange,
  onPreview,
  onReset,
  label,
  className,
}: SplitDividerProps) {
  const drag = useRef<{
    pointerId: number;
    startX: number;
    startValue: number;
    last: number | null;
  } | null>(null);
  const [dragging, setDragging] = useState(false);

  const endDrag = (el: HTMLElement) => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setDragging(false);
    if (onPreview && d.last !== null) onChange(d.last);
    document.body.classList.remove(...DRAGGING_BODY_CLASSES);
    try {
      if (el.hasPointerCapture?.(d.pointerId)) el.releasePointerCapture(d.pointerId);
    } catch {
      // The capture is already gone (pointer cancelled); nothing to release.
    }
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    // No text selection starts, and focus still lands on the divider.
    e.preventDefault();
    e.currentTarget.focus();
    drag.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startValue: value,
      last: null,
    };
    setDragging(true);
    document.body.classList.add(...DRAGGING_BODY_CLASSES);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // An environment without capture still drags while over the line.
    }
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || e.pointerId !== d.pointerId) return;
    const raw = d.startValue + (e.clientX - d.startX);
    const next = clampWidth(raw, min, max);
    if (onPreview) {
      d.last = next;
      onPreview(next);
    } else onChange(next);
  };

  const onPointerEnd = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current && e.pointerId === drag.current.pointerId) endDrag(e.currentTarget);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    let next: number | null = null;
    if (e.key === "ArrowLeft") next = value - KEYBOARD_STEP;
    else if (e.key === "ArrowRight") next = value + KEYBOARD_STEP;
    else if (e.key === "Home") next = min;
    else if (e.key === "End" && Number.isFinite(max)) next = max;
    if (next === null) return;
    e.preventDefault();
    onChange(clampWidth(next, min, max));
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={Math.round(value)}
      aria-valuemin={Math.round(min)}
      aria-valuemax={Number.isFinite(max) ? Math.round(Math.max(min, max)) : undefined}
      tabIndex={0}
      data-dragging={dragging ? "true" : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onLostPointerCapture={onPointerEnd}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      className={cn(
        // The 1px hairline; it takes 1px in the row and never shrinks.
        "group relative z-sticky w-px shrink-0 cursor-col-resize touch-none self-stretch bg-border outline-none",
        // The invisible 12px hit area, centred on the line.
        "before:absolute before:inset-y-0 before:-inset-x-[5.5px] before:content-['']",
        // The 2px accent line, centred on the hairline: hover, drag, focus.
        "after:pointer-events-none after:absolute after:inset-y-0 after:-inset-x-[0.5px] after:bg-accent after:opacity-0 after:transition-opacity after:duration-fast after:content-['']",
        "hover:after:opacity-100 focus-visible:after:opacity-100 data-[dragging=true]:after:opacity-100",
        "focus-visible:ring-2 focus-visible:ring-focus-ring",
        className,
      )}
    />
  );
}
