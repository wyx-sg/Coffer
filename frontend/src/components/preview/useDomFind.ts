// src/components/preview/useDomFind.ts
// Wires the shared find controller (useFind) to a rendered-DOM container via the
// CSS Custom Highlight API (domFind.ts). Reused by <FindableMarkdown> for .md
// previews and by the chat transcript so Cmd/Ctrl+F finds across rendered text
// the same way everywhere. Returns the find state, the input ref to focus, and a
// keydown handler to attach to the (focusable) scroll container.
import { type KeyboardEvent, type RefObject, useCallback, useEffect, useMemo, useRef } from "react";

import { applyHighlights, clearHighlights, findRanges, scrollRangeIntoView } from "./domFind";
import { useFind, type Find, type FindEngine } from "./useFind";

export interface DomFind {
  find: Find;
  inputRef: RefObject<HTMLInputElement>;
  onKeyDown: (e: KeyboardEvent<HTMLElement>) => void;
}

export function useDomFind(
  containerRef: RefObject<HTMLElement | null>,
  revision?: unknown,
): DomFind {
  const rangesRef = useRef<Range[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const engine = useMemo<FindEngine>(
    () => ({
      apply(query, caseSensitive) {
        const container = containerRef.current;
        if (!container) return 0;
        rangesRef.current = findRanges(container, query, caseSensitive);
        applyHighlights(rangesRef.current, -1);
        return rangesRef.current.length;
      },
      setActive(index) {
        applyHighlights(rangesRef.current, index);
        scrollRangeIntoView(rangesRef.current[index]);
      },
      clear() {
        rangesRef.current = [];
        clearHighlights();
      },
    }),
    [containerRef],
  );

  const find = useFind(engine, revision);

  useEffect(() => {
    if (find.open) inputRef.current?.focus();
  }, [find.open]);

  // Clear any lingering highlights if the host unmounts while find is open.
  useEffect(() => () => clearHighlights(), []);

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLElement>) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "f" || e.key === "F")) {
        e.preventDefault();
        find.openFind();
        inputRef.current?.focus();
      } else if (e.key === "Escape" && find.open) {
        e.preventDefault();
        find.closeFind();
      }
    },
    [find],
  );

  return { find, inputRef, onKeyDown };
}
