// src/lib/hooks/useResizableWidth.ts — a split pane's width: clamped to its bounds, remembered per page.
//
// Every split view (list beside detail, tree beside file, the sidebar beside
// the workspace) keeps the width its divider was dragged to in this viewer's
// browser storage under `coffer.split.<storageKey>`. It is a convenience, not
// state that must survive: every read and write is wrapped, so a missing,
// unreadable or blocked storage just means "open at the default".
//
// The hook keeps the width the viewer ASKED for and clamps it against the
// bounds on every render, so a remembered width that no longer fits the window
// opens clamped, and a window that shrinks and grows back returns to the width
// the viewer chose.
import { useCallback, useState } from "react";

const STORAGE_PREFIX = "coffer.split.";

// List/detail bounds (spec web-ui "Resize every split view by its divider"):
// the list at least 240px and at most half the split, the detail at least 480px.
export const LIST_MIN_WIDTH = 240;
export const DETAIL_MIN_WIDTH = 480;
export const DEFAULT_LIST_WIDTH = 320;

/** The list's upper bound in a split `containerWidth` px wide: half of it, or
 *  what leaves the detail its minimum — whichever is less. */
export function listMaxWidth(containerWidth: number): number {
  return Math.min(containerWidth / 2, containerWidth - DETAIL_MIN_WIDTH);
}

/** Clamp `value` into [min, max], rounded to whole px. When the bounds cross
 *  (a container too narrow for both minimums) the lower bound wins, so the
 *  pane keeps its minimum and the rest of the row gives way. */
export function clampWidth(value: number, min: number, max: number): number {
  const v = Number.isFinite(value) ? value : min;
  return Math.round(Math.max(min, Math.min(v, max)));
}

function storageKeyFor(key: string): string {
  return `${STORAGE_PREFIX}${key}`;
}

function readStored(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(storageKeyFor(key));
    if (raw === null) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, value: number | null): void {
  try {
    if (value === null) window.localStorage.removeItem(storageKeyFor(key));
    else window.localStorage.setItem(storageKeyFor(key), String(value));
  } catch {
    // Storage blocked or full: the width still applies for this visit.
  }
}

export interface ResizableWidthOptions {
  /** Names the split, e.g. "chat.list"; stored as `coffer.split.<storageKey>`. */
  storageKey: string;
  /** Width in px the split opens at when nothing is remembered, and after a reset. */
  defaultWidth: number;
  /** Narrowest the pane may be (px). */
  min: number;
  /** Widest the pane may be (px); the caller computes it (e.g. from its
   *  container). Omitted or non-finite means no upper bound. */
  max?: number;
}

export interface ResizableWidth {
  /** The width to render, already clamped to `bounds`. */
  width: number;
  /** Set a new width: clamped to the bounds, then remembered. */
  setWidth: (next: number) => void;
  /** Back to `defaultWidth`, and forget the remembered width so the next
   *  visit opens at the default too. */
  reset: () => void;
  bounds: { min: number; max: number };
}

export function useResizableWidth({
  storageKey,
  defaultWidth,
  min,
  max,
}: ResizableWidthOptions): ResizableWidth {
  const upper = max !== undefined && Number.isFinite(max) ? max : Number.POSITIVE_INFINITY;
  const [state, setState] = useState(() => ({ key: storageKey, wanted: readStored(storageKey) }));

  // A different split on the same component instance: read its own width.
  let wanted = state.wanted;
  if (state.key !== storageKey) {
    wanted = readStored(storageKey);
    setState({ key: storageKey, wanted });
  }

  const width = clampWidth(wanted ?? defaultWidth, min, upper);

  const setWidth = useCallback(
    (next: number) => {
      const clamped = clampWidth(next, min, upper);
      setState({ key: storageKey, wanted: clamped });
      writeStored(storageKey, clamped);
    },
    [storageKey, min, upper],
  );

  const reset = useCallback(() => {
    setState({ key: storageKey, wanted: null });
    writeStored(storageKey, null);
  }, [storageKey]);

  return { width, setWidth, reset, bounds: { min, max: upper } };
}
