// src/components/preview/FindableMarkdown.tsx
// Rendered-Markdown preview with the same Cmd/Ctrl+F find as <CodeView>. It wraps
// the shared <Markdown> renderer and the unified <FindWidget>, driving matches
// through the CSS Custom Highlight API (domFind.ts) so finding works on the
// rendered output without touching the DOM react-markdown owns. Used by every
// .md preview (KB document, memory fact, skill Markdown files).
import { useEffect, useMemo, useRef } from "react";

import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import { applyHighlights, clearHighlights, findRanges, scrollRangeIntoView } from "./domFind";
import { FindWidget } from "./FindWidget";
import { useFind, type FindEngine } from "./useFind";

interface FindableMarkdownProps {
  /** Markdown source to render read-only. */
  children: string;
  /** Classes for the scroll viewport (height + overflow + padding). */
  className?: string;
}

export function FindableMarkdown({ children, className }: FindableMarkdownProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const rangesRef = useRef<Range[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const engine = useMemo<FindEngine>(
    () => ({
      apply(query, caseSensitive) {
        const container = scrollRef.current;
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
    [],
  );

  const find = useFind(engine);

  useEffect(() => {
    if (find.open) inputRef.current?.focus();
  }, [find.open]);

  // Clear any lingering highlights if the preview unmounts while open.
  useEffect(() => () => clearHighlights(), []);

  return (
    <div className="relative">
      <div
        ref={scrollRef}
        tabIndex={0}
        className={cn("outline-none", className)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && (e.key === "f" || e.key === "F")) {
            e.preventDefault();
            find.openFind();
            inputRef.current?.focus();
          } else if (e.key === "Escape" && find.open) {
            e.preventDefault();
            find.closeFind();
          }
        }}
      >
        <Markdown>{children}</Markdown>
      </div>
      {find.open ? (
        <FindWidget
          ref={inputRef}
          query={find.query}
          count={find.count}
          active={find.active}
          caseSensitive={find.caseSensitive}
          onQueryChange={find.setQuery}
          onToggleCase={find.toggleCaseSensitive}
          onNext={find.next}
          onPrev={find.prev}
          onClose={find.closeFind}
        />
      ) : null}
    </div>
  );
}
