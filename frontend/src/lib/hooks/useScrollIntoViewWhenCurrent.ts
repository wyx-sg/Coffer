// src/lib/hooks/useScrollIntoViewWhenCurrent.ts — keep a list's open row in sight.
//
// A page opened at an item's address (from Overview's Needs you, a link
// elsewhere, a reload) selects that item's row, but in a long list the row
// may sit below the fold. The row puts this ref on itself: when it becomes the
// current one it scrolls its list just far enough to show it ("nearest", so a
// row already in view does not move).
import { useEffect, useRef } from "react";

export function useScrollIntoViewWhenCurrent<T extends HTMLElement>(current: boolean) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (current) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [current]);
  return ref;
}
