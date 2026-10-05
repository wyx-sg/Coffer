// frontend/src/lib/rowClick.ts
// One rule for "click anywhere on a list row to open its detail". The row's
// name stays a real link/button (keyboard, middle-click and Cmd-click work on
// it) and is marked `data-row-open`; a click on the rest of the row forwards to
// that element. A click is left alone when it landed on a control that does its
// own thing (button, link, input, switch, menu item, checkbox, anything marked
// `data-row-ignore`), when it carries a modifier key, when it ends a text
// selection drag, or when it bubbled up from a portal (a menu or dialog).
import type { MouseEvent } from "react";

const INTERACTIVE =
  "button,a,input,select,textarea,label,[role=switch],[role=menuitem],[role=checkbox],[role=combobox],[role=option],[data-row-ignore]";

/** True when a click on a row must not open the row's detail. */
export function shouldIgnoreRowClick(e: MouseEvent<HTMLElement>): boolean {
  if (e.defaultPrevented || e.button !== 0) return true;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return true;
  const row = e.currentTarget;
  const target = e.target as Element | null;
  if (!target || !row.contains(target)) return true;
  if (target.closest(INTERACTIVE)) return true;
  const selection = window.getSelection();
  if (selection && !selection.isCollapsed && selection.toString() !== "") {
    const anchor = selection.anchorNode;
    if (anchor && row.contains(anchor)) return true;
  }
  return false;
}

/** Row `onClick`: forward a plain click on the row to its `data-row-open` element. */
export function openRowTarget(e: MouseEvent<HTMLElement>): void {
  if (shouldIgnoreRowClick(e)) return;
  e.currentTarget.querySelector<HTMLElement>("[data-row-open]")?.click();
}
