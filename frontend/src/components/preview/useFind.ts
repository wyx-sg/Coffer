// src/components/preview/useFind.ts
// Shared find-state controller behind the unified <FindWidget>. It owns the
// open/query/case/count/active state and re-applies the query through a pluggable
// FindEngine; <CodeView> and <FindableMarkdown> supply the engine (CodeMirror
// decorations vs. CSS Highlight API) so the find UX is byte-identical everywhere.
import { useCallback, useEffect, useState } from "react";

export interface FindEngine {
  /** Paint every match for `query`; return the match count (active starts unset). */
  apply(query: string, caseSensitive: boolean): number;
  /** Mark + scroll the match at `index` (0-based). */
  setActive(index: number): void;
  /** Remove all find highlights. */
  clear(): void;
}

export interface Find {
  open: boolean;
  query: string;
  caseSensitive: boolean;
  count: number;
  /** 0-based index of the active match, or -1 when there are none. */
  active: number;
  setQuery: (value: string) => void;
  toggleCaseSensitive: () => void;
  openFind: () => void;
  closeFind: () => void;
  next: () => void;
  prev: () => void;
}

/**
 * @param engine   the backend that paints/navigates matches (CodeMirror or DOM).
 * @param revision a value that changes when the previewed content changes; when
 *   it does, an open search re-applies against the new content so the count and
 *   match offsets never go stale (e.g. switching files in the same CodeView).
 */
export function useFind(engine: FindEngine | null, revision?: unknown): Find {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [count, setCount] = useState(0);
  const [active, setActive] = useState(-1);

  // Re-run the search whenever the query, case mode, engine, open state, or the
  // previewed content (revision) changes. A blank query (or a closed widget)
  // clears any existing highlights.
  useEffect(() => {
    if (!engine) return;
    if (!open || query === "") {
      engine.clear();
      setCount(0);
      setActive(-1);
      return;
    }
    const n = engine.apply(query, caseSensitive);
    setCount(n);
    if (n > 0) {
      engine.setActive(0);
      setActive(0);
    } else {
      setActive(-1);
    }
  }, [engine, open, query, caseSensitive, revision]);

  const openFind = useCallback(() => setOpen(true), []);

  const closeFind = useCallback(() => {
    setOpen(false);
    setQuery("");
    engine?.clear();
    setCount(0);
    setActive(-1);
  }, [engine]);

  const step = useCallback(
    (delta: number) => {
      setActive((cur) => {
        if (count === 0) return -1;
        const nextIndex = (cur + delta + count) % count;
        engine?.setActive(nextIndex);
        return nextIndex;
      });
    },
    [count, engine],
  );

  const next = useCallback(() => step(1), [step]);
  const prev = useCallback(() => step(-1), [step]);
  const toggleCaseSensitive = useCallback(() => setCaseSensitive((v) => !v), []);

  return {
    open,
    query,
    caseSensitive,
    count,
    active,
    setQuery,
    toggleCaseSensitive,
    openFind,
    closeFind,
    next,
    prev,
  };
}
