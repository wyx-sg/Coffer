// frontend/src/kinds/memory/MemoryPreviewBody.tsx
//
// Shared preview body for the memory lanes + fact viewer. Splits a leading YAML
// frontmatter block off the text (so `---` fences don't render as <hr>), shows
// the parsed `title`/`description` plus a small muted meta line
// (`updated_at`/`branch`/`period`) as a clean header, and renders ONLY the body
// through <FindableMarkdown>. With no frontmatter the header is empty and the
// text flows through unchanged.
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { splitFrontmatter } from "./frontmatter";

// Frontmatter keys surfaced in the small muted meta line, in display order.
const META_KEYS = ["updated_at", "branch", "period"] as const;

interface Props {
  /** Raw file text (may begin with a `---` frontmatter block). */
  text: string;
  /** Classes for the FindableMarkdown scroll viewport. */
  className?: string;
  /** Recall query to pre-highlight in the body ("" = no highlight). */
  initialQuery?: string;
  /**
   * A `description` already shown by the surface's own header (the fact viewer
   * renders `fact.description` itself). When true the header's `description`
   * line is suppressed to avoid showing it twice.
   */
  hideDescription?: boolean;
}

export function MemoryPreviewBody({ text, className, initialQuery, hideDescription }: Props) {
  const { meta, body } = splitFrontmatter(text);
  const title = meta.title;
  const description = hideDescription ? undefined : meta.description;
  const metaLine = META_KEYS.filter((k) => meta[k])
    .map((k) => meta[k])
    .join(" · ");

  return (
    <>
      {title || description || metaLine ? (
        <div className="space-y-1 border-b border-border px-4 py-2.5">
          {title ? <p className="font-medium leading-tight">{title}</p> : null}
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
          {metaLine ? <p className="text-xs text-muted-foreground">{metaLine}</p> : null}
        </div>
      ) : null}
      <FindableMarkdown className={className} initialQuery={initialQuery}>
        {body}
      </FindableMarkdown>
    </>
  );
}
