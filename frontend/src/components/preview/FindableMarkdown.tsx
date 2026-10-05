// src/components/preview/FindableMarkdown.tsx
// Rendered-Markdown preview with the same Cmd/Ctrl+F find as <CodeView>. It wraps
// the shared <Markdown> renderer plus the unified <FindWidget>, driving matches
// through the CSS Custom Highlight API (useDomFind) so finding works on the
// rendered output without touching the DOM react-markdown owns. Used by every
// .md preview (KB document, skill Markdown files, an agent's
// memory store).
//
// A file's leading YAML frontmatter is shown as METADATA above the body — a
// key / value grid (mono 11 keys in a 96 column, 12 values; Foundations 0.6.03) — never rendered as body text
// (spec memory "Show a partition's memories read-only"). Rendered raw,
// the fences became rules and `origins:` became a bullet list that read as if
// it were part of the note. Done once here so every Markdown preview gets it.
import { useRef } from "react";

import { Markdown } from "@/components/Markdown";
import { splitFrontmatter, type FrontmatterEntry } from "@/lib/preview/frontmatter";
import { cn } from "@/lib/utils";
import { FindWidget } from "./FindWidget";
import { useDomFind } from "./useDomFind";

interface FindableMarkdownProps {
  /** Markdown source to render read-only. */
  children: string;
  /** Classes for the scroll viewport (border, background, padding; with
   *  `fill` unset, also its height + overflow). */
  className?: string;
  /** Take the remaining height of a flex column and scroll inside it — how a
   *  file pane's preview fills the window (components/filePane.ts). */
  fill?: boolean;
  /** Split a leading frontmatter block off as metadata (default). Off for
   *  text that is not a file — a chat turn opening with `---` is prose. */
  frontmatter?: boolean;
  /** When set, pre-seed the find query to highlight this term (e.g. a recall /
   *  search hit). Empty string closes/clears; `undefined` leaves find as the
   *  Cmd/Ctrl+F-only default. */
  initialQuery?: string;
}

function FrontmatterList({ entries }: { entries: FrontmatterEntry[] }) {
  return (
    <dl
      data-testid="markdown-frontmatter"
      className="mb-4 grid grid-cols-[96px_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-b border-border-subtle pb-3"
    >
      {entries.map(({ key, value }) => (
        <div key={key} className="contents">
          <dt className="font-mono text-2xs leading-[18px] text-text-subtle">{key}</dt>
          <dd className="min-w-0 whitespace-pre-wrap break-words text-xs leading-[18px] text-text">
            {Array.isArray(value) ? (
              <ul className="space-y-0.5">
                {value.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            ) : (
              value
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function FindableMarkdown({
  children,
  className,
  fill = false,
  frontmatter = true,
  initialQuery,
}: FindableMarkdownProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // Pass the markdown source as the revision so an open search re-applies when
  // the previewed document changes (e.g. selecting a different KB doc / fact).
  const { find, inputRef, onKeyDown } = useDomFind(scrollRef, children, initialQuery);
  const { entries, body } = frontmatter
    ? splitFrontmatter(children)
    : { entries: [], body: children };

  return (
    <div className={cn("relative", fill && "flex min-h-0 flex-1 flex-col")}>
      <div
        ref={scrollRef}
        tabIndex={0}
        className={cn("outline-none", fill && "min-h-0 flex-1 overflow-auto", className)}
        onKeyDown={onKeyDown}
      >
        {/* Constrain the rendered body to a comfortable reading width (centered)
            so long lines don't stretch edge-to-edge on wide screens. */}
        <div className="mx-auto max-w-3xl">
          {entries.length > 0 ? <FrontmatterList entries={entries} /> : null}
          <Markdown>{body}</Markdown>
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
