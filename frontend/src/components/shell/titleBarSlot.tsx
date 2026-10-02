// src/components/shell/titleBarSlot.tsx — where a page's "← back" link goes in the desktop shell.
//
// The desktop window draws its own title bar (WindowTitleStrip). A detail
// page's way back belongs there, beside the sidebar toggle, rather than as a
// row above the page's title. The strip registers the element it leaves for it
// (`TitleBarSlotContext`); `InTitleBar` portals its children into it. With no
// slot — a browser tab, Windows, Linux — the children simply render where they
// are, so the same page code serves both.
import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";

export const TitleBarSlotContext = createContext<HTMLElement | null>(null);

export function InTitleBar({ children }: { children: ReactNode }) {
  const slot = useContext(TitleBarSlotContext);
  return slot ? createPortal(children, slot) : <>{children}</>;
}
