// src/lib/hooks/useSplitCollapsed.ts — whether a split view's list pane is folded away, remembered per page.
//
// Kept under `coffer.split.<storageKey>.collapsed` ("1" / "0") beside the
// remembered width (`coffer.split.<storageKey>`), which a collapse never
// touches: expanding returns the list to the width the viewer last chose. Like
// the width it is a per-browser convenience — every read and write is wrapped,
// and blocked storage just means "expanded, and the choice holds for this visit".
import { useCallback, useState } from "react";

const STORAGE_PREFIX = "coffer.split.";

function storageKeyFor(key: string): string {
  return `${STORAGE_PREFIX}${key}.collapsed`;
}

function readCollapsed(key: string): boolean {
  try {
    return window.localStorage.getItem(storageKeyFor(key)) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(key: string, collapsed: boolean): void {
  try {
    if (collapsed) window.localStorage.setItem(storageKeyFor(key), "1");
    else window.localStorage.removeItem(storageKeyFor(key));
  } catch {
    // Storage blocked or full: the choice still applies for this visit.
  }
}

/** @ui-only hook result; never crosses the wire. */
export interface SplitCollapsed {
  collapsed: boolean;
  setCollapsed: (next: boolean) => void;
}

export function useSplitCollapsed(storageKey: string): SplitCollapsed {
  const [state, setState] = useState(() => ({
    key: storageKey,
    collapsed: readCollapsed(storageKey),
  }));

  // A different split on the same component instance: read its own flag.
  let collapsed = state.collapsed;
  if (state.key !== storageKey) {
    collapsed = readCollapsed(storageKey);
    setState({ key: storageKey, collapsed });
  }

  const setCollapsed = useCallback(
    (next: boolean) => {
      setState({ key: storageKey, collapsed: next });
      writeCollapsed(storageKey, next);
    },
    [storageKey],
  );

  return { collapsed, setCollapsed };
}
