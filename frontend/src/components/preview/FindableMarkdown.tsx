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
}

export function FindableMarkdown({ children, className }: FindableMarkdownProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { find, inputRef, onKeyDown } = useDomFind(scrollRef);

  return (
    <div className="relative">
      <div
        ref={scrollRef}
        tabIndex={0}
        className={cn("outline-none", className)}
        onKeyDown={onKeyDown}
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
