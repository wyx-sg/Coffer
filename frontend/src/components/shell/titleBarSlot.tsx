// src/components/shell/titleBarSlot.tsx — where an open conversation's title goes in the desktop shell.
//
// The window title bar (WindowTitleStrip) holds only window controls — with one
// exception: the open conversation's title, its source and its ⋯ menu sit in it,
// beside the sidebar (Shell board 1.1.02, Run 3.1.17–23). The strip registers the
// element it leaves for them (`TitleBarSlotContext`); `InTitleBar` portals its
// children into it. With no slot — a browser tab, Windows, Linux — the children
// render where they are, so the same page code serves both. Only the
// conversation page uses this.
import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";

// eslint-disable-next-line react-refresh/only-export-components -- the context and its portal helper belong together
export const TitleBarSlotContext = createContext<HTMLElement | null>(null);

/** The title row: in the desktop title bar when there is one, else a 44px bar at the top of the content. */
export function InTitleBar({ children }: { children: ReactNode }) {
  const slot = useContext(TitleBarSlotContext);
  if (slot) return createPortal(children, slot);
  return (
    <div data-testid="content-title-bar" className="flex h-11 shrink-0 items-center gap-2.5 px-8">
      {children}
    </div>
  );
}
