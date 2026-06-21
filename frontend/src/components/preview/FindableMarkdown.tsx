// src/components/preview/FindableMarkdown.tsx
// Rendered-Markdown preview with the same Cmd/Ctrl+F find as <CodeView>. It wraps
// the shared <Markdown> renderer plus the unified <FindWidget>, driving matches
// through the CSS Custom Highlight API (useDomFind) so finding works on the
// rendered output without touching the DOM react-markdown owns. Used by every
// .md preview (KB document, memory fact, skill Markdown files).
import { useRef } from "react";

import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import { FindWidget } from "./FindWidget";
import { useDomFind } from "./useDomFind";

interface FindableMarkdownProps {
  /** Markdown source to render read-only. */
  children: string;
  /** Classes for the scroll viewport (height + overflow + padding). */
  className?: string;
  /** When set, pre-seed the find query to highlight this term (e.g. a recall /
   *  search hit). Empty string closes/clears; `undefined` leaves find as the
   *  Cmd/Ctrl+F-only default. */
  initialQuery?: string;
}

export function FindableMarkdown({ children, className, initialQuery }: FindableMarkdownProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // Pass the markdown source as the revision so an open search re-applies when
  // the previewed document changes (e.g. selecting a different KB doc / fact).
  const { find, inputRef, onKeyDown } = useDomFind(scrollRef, children, initialQuery);

  return (
    <div className="relative">
      <div
        ref={scrollRef}
        tabIndex={0}
        className={cn("outline-none", className)}
        onKeyDown={onKeyDown}
      >
        {/* Constrain the rendered body to a comfortable reading width (centered)
            so long lines don't stretch edge-to-edge on wide screens. */}
        <div className="mx-auto max-w-3xl">
          <Markdown>{children}</Markdown>
        </div>
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
