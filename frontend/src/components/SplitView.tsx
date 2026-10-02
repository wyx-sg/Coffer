// src/components/SplitView.tsx — a list pane beside a detail pane, resizable by the divider between them.
//
// Bounds (spec web-ui "Resize every split view by its divider"): the list is
// at least `LIST_MIN_WIDTH`, at most half the split, and never so wide that
// the detail drops under `DETAIL_MIN_WIDTH` — whichever upper bound comes
// first; the list gives way before the detail does. When the split is too
// narrow for both minimums the list keeps its minimum and the detail shrinks.
// The split measures its own width (ResizeObserver, plus window resize where
// ResizeObserver is missing or stubbed) and re-clamps as it shrinks; until it
// has a measurement (or has no layout, as in jsdom) only the minimum applies.
import { memo, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { SplitDivider } from "@/components/SplitDivider";
import {
  DEFAULT_LIST_WIDTH,
  LIST_MIN_WIDTH,
  listMaxWidth,
  useResizableWidth,
} from "@/lib/hooks/useResizableWidth";
import { cn } from "@/lib/utils";

// The list pane, memoised: while the divider is dragged only its inline width
// changes (set directly on the element), so neither pane's content is
// re-rendered per frame, and no width transition runs (none is declared).
const Pane = memo(function Pane({ children }: { children: ReactNode }) {
  return <>{children}</>;
});

export interface SplitViewProps {
  /** Names this split for the remembered width (`coffer.split.<storageKey>`). */
  storageKey: string;
  defaultListWidth?: number;
  list: ReactNode;
  detail: ReactNode;
  /** The divider's accessible name, e.g. t("splitView.resizeList"). */
  label: string;
  /** Hide the list pane and its divider; the detail keeps its place in the
   *  tree (so it is not remounted) and takes the whole row. */
  listHidden?: boolean;
  className?: string;
  /** Classes for the list pane (its surface, its own layout). */
  listClassName?: string;
  /** Classes for the detail pane. */
  detailClassName?: string;
}

export function SplitView({
  storageKey,
  defaultListWidth = DEFAULT_LIST_WIDTH,
  list,
  detail,
  label,
  listHidden = false,
  className,
  listClassName,
  detailClassName,
}: SplitViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const update = () => {
      const w = el.getBoundingClientRect().width;
      // 0 = no layout (hidden, or jsdom): no measurement rather than "0px wide".
      setContainerWidth(w > 0 ? w : null);
    };
    update();
    window.addEventListener("resize", update);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => update());
    observer?.observe(el);
    return () => {
      window.removeEventListener("resize", update);
      observer?.disconnect();
    };
  }, []);

  const { width, setWidth, reset, bounds } = useResizableWidth({
    storageKey,
    defaultWidth: defaultListWidth,
    min: LIST_MIN_WIDTH,
    max: containerWidth === null ? undefined : listMaxWidth(containerWidth),
  });

  return (
    <div ref={rootRef} className={cn("flex min-w-0 flex-row", className)}>
      {listHidden ? null : (
        <>
          <div
            // A width in px from state has no class to hold it: the one inline
            // style, bridging the dragged width onto the pane.
            ref={listRef}
            id={listId}
            style={{ width }}
            className={cn("flex min-h-0 shrink-0 flex-col", listClassName)}
          >
            <Pane>{list}</Pane>
          </div>
          <SplitDivider
            value={width}
            min={bounds.min}
            max={bounds.max}
            onChange={setWidth}
            // A drag moves the pane's width on the element itself; React (and
            // the remembered width) hear of it once, when the pointer lifts.
            onPreview={(next) => {
              if (listRef.current) listRef.current.style.width = `${next}px`;
            }}
            // A 1px line with a 12px gutter each side: the panes' content never touches it.
            className="mx-3"
            onReset={reset}
            label={label}
          />
        </>
      )}
      <div className={cn("flex min-h-0 min-w-0 flex-1 flex-col", detailClassName)}>
        <Pane>{detail}</Pane>
      </div>
    </div>
  );
}
