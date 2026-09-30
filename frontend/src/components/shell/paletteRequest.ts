// src/components/shell/paletteRequest.ts — lets a page open the command palette the shell owns.
//
// The palette's open state is Layout's (⌘K and the sidebar search control
// toggle it there). A page that offers "Search Coffer ⌘K" — the 404 page,
// board 1.2.16 — asks for it through this one window event instead of
// reaching into the shell.
import { useEffect } from "react";

const EVENT = "coffer:open-palette";

/** Open the command palette over the current page. */
export function requestPalette(): void {
  window.dispatchEvent(new Event(EVENT));
}

/** Layout: open the palette when a page asks. */
export function usePaletteRequests(open: () => void): void {
  useEffect(() => {
    window.addEventListener(EVENT, open);
    return () => window.removeEventListener(EVENT, open);
  }, [open]);
}
