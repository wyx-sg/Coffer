// frontend/src/components/filePane.ts
//
// One rule for every pane that browses files: the file trees (skill,
// knowledge, memory partition, an agent's memory store, an agent's config
// files, a transcript's outline) and the previews beside them END AT THE
// BOTTOM OF THE WINDOW and scroll inside, whatever the window's size.
//
// It used to be a cap (`max-h-[60vh]`): a fraction of the window, chosen so the
// header above would still fit. On a tall window that left a third of the
// screen empty under a preview that was scrolling anyway; on a short one it
// still pushed the page into scrolling. The height a pane should have is not a
// fraction of anything — it is "whatever is left under what sits above it", so
// it is measured rather than guessed.
//
// How: `useFillToBottom` is put on the two-pane grid. It measures where the
// grid starts inside the app's scrolling page wrapper (Layout.tsx: the shell pins
// the app to the viewport, and the page wrapper under the status bar is the one
// scroll container), and what
// sits BELOW it (a pager, the page's bottom padding), and gives the grid
// exactly the height in between — so the page itself does not scroll, and both
// columns end on the same line. It re-measures when the window resizes and
// when anything in the page changes size (a header wrapping, a banner). A
// floor of `FILE_PANE_MIN_HEIGHT` keeps a very short window usable: there the
// page scrolls to the pane rather than the pane shrinking to nothing.
//
// Inside the grid, each column is a flex column (`FILE_PANE_COLUMN`): its fixed
// rows (a label, a path, an action bar) keep their size and the one scrolling
// region takes the rest (`FILE_PANE_SCROLL`). Below `md` the columns stack, and
// the grid's two rows split the same height between tree and preview.
import { useCallback, useLayoutEffect, useState, type CSSProperties } from "react";

/** One column of that grid: fixed rows on top, one scrolling region below. */
export const FILE_PANE_COLUMN = "flex min-h-0 min-w-0 flex-col gap-2";

/** The part of a column that scrolls — it takes whatever height is left. */
export const FILE_PANE_SCROLL = "min-h-0 flex-1 overflow-auto";

/** Below this the pane stops shrinking (px; 20rem). */
const FILE_PANE_MIN_HEIGHT = 320;

/** The element the page scrolls in: the nearest ancestor whose overflow-y
 *  scrolls. Layout.tsx puts `overflow-y-auto` on a wrapper INSIDE `<main>`
 *  (under the daemon status bar), so `<main>` itself is not the scroller;
 *  measuring against it left the pane's height off by the bar and the page's
 *  padding. `<main>` stays the fallback where no style says (a test, a bare
 *  page). */
export function scrollContainer(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const overflowY = window.getComputedStyle(node).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") return node;
  }
  return el.closest("main");
}

function measure(el: HTMLElement): number {
  const scroller = scrollContainer(el);
  const rect = el.getBoundingClientRect();
  // Outside the app shell (a test, a bare page) the window is the container.
  if (!scroller) return Math.floor(window.innerHeight - rect.top);
  const scrollerRect = scroller.getBoundingClientRect();
  // Where the element starts within the scroll container's CONTENT, so the
  // answer is the same however far the page happens to be scrolled.
  const top = rect.top - scrollerRect.top + scroller.scrollTop;
  // What sits under it: everything between its bottom edge and the end of the
  // page content, plus that content's own bottom padding.
  const content = scroller.firstElementChild as HTMLElement | null;
  let below = 0;
  if (content) {
    const contentRect = content.getBoundingClientRect();
    below = Math.max(0, contentRect.bottom - rect.bottom);
  }
  return Math.floor(scroller.clientHeight - top - below);
}

/**
 * Size an element to reach the bottom of the window. Spread the result onto
 * the two-pane grid: `ref` measures it, `style` carries the height.
 *
 * `style` is an inline height on purpose — it is a measured number, not a
 * design token, and there is no class that could hold it.
 */
export function useFillToBottom<T extends HTMLElement = HTMLDivElement>(): {
  ref: (el: T | null) => void;
  style: CSSProperties;
} {
  const [el, setEl] = useState<T | null>(null);
  const [height, setHeight] = useState<number | null>(null);
  const ref = useCallback((node: T | null) => setEl(node), []);

  useLayoutEffect(() => {
    if (!el) return;
    const update = () => setHeight(Math.max(FILE_PANE_MIN_HEIGHT, measure(el)));
    update();
    window.addEventListener("resize", update);
    const scroller = scrollContainer(el);
    const observed = [scroller, scroller?.firstElementChild].filter(
      (n): n is Element => n instanceof Element,
    );
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => update());
    for (const node of observed) observer?.observe(node);
    return () => {
      window.removeEventListener("resize", update);
      observer?.disconnect();
    };
  }, [el]);

  return { ref, style: height === null ? {} : { height } };
}
