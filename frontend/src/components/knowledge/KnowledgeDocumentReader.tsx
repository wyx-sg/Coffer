// frontend/src/components/knowledge/KnowledgeDocumentReader.tsx
//
// The open file, read-only (boards 5.1.01, 0.6.03): in one reading column,
// 720 wide and centred — its title (the body's own leading `# Heading` when it
// has one, so the page never shows two), then ONE quiet line of what it is
// (KnowledgeFileLine: a page's type and sources, a source's citing pages or
// Waiting mark, who created it and when), then the body.
// Preview renders the Markdown, a page's `[[links]]` opening the file each
// resolves to (KnowledgeWikiLink); Source shows the raw text in the code
// viewer. A picture the Markdown links by a relative path (an upload's,
// under `assets/`) shows inline (KnowledgeImage). Every file is the same here, whoever wrote it last (spec knowledge
// "Let only a person delete a document"); its file actions live in the pane
// bar, not beside the text.
//
// Inline code reads as part of the sentence — a light tint, a size relative to
// the text around it — and a long path or identifier breaks after each `/`,
// `.` or `_` rather than running out of the column; a fenced block keeps the
// shared code style.
import { Fragment, useMemo, type ReactNode } from "react";
import type { Components } from "react-markdown";

import { KnowledgeFileLine } from "@/components/knowledge/KnowledgeFileLine";
import { KnowledgeImage } from "@/components/knowledge/KnowledgeImage";
import { KnowledgeWikiLink } from "@/components/knowledge/KnowledgeWikiLink";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { FileOut } from "@/lib/api/knowledge";
import { resolveAsset } from "@/lib/knowledge/assets";
import { splitTitleHeading } from "@/lib/knowledge/titleHeading";
import { markWikiLinks, wikiTargetOf } from "@/lib/knowledge/wikiLinks";

/** `a/b/c.md` with a break opportunity after each `/`, `.`, `_` and `-`, so a
 *  long path wraps at its separators instead of overflowing or mid-word. */
function breakable(text: string): ReactNode {
  const parts = text.split(/(?<=[/._-])/);
  if (parts.length < 2) return text;
  return parts.map((part, i) => (
    <Fragment key={i}>
      {part}
      {i < parts.length - 1 ? <wbr /> : null}
    </Fragment>
  ));
}

/** Inline code as part of the sentence; a fenced block as the shared renderer has it. */
const code: Components["code"] = ({ className, children, ...props }) => {
  if (String(className ?? "").includes("language-")) {
    return (
      <code className={`${className ?? ""} font-mono text-xs leading-[1.6]`} {...props}>
        {children}
      </code>
    );
  }
  return (
    <code
      data-testid="inline-code"
      className="rounded-[4px] bg-surface-sunken px-[0.3em] py-[0.1em] font-mono text-[0.88em] text-text [overflow-wrap:anywhere]"
      {...props}
    >
      {typeof children === "string" ? breakable(children) : children}
    </code>
  );
};

interface Props {
  file: FileOut;
  /** The collection the file is in: a link opens its target there. */
  collectionUid: string;
  /** Show the raw text instead of the rendered Markdown. */
  source: boolean;
}

export function KnowledgeDocumentReader({ file, collectionUid, source }: Props) {
  const { title, body } = useMemo(
    () => splitTitleHeading(file.body, file.title),
    [file.body, file.title],
  );
  const page = file.kind === "page";
  const rendered = useMemo(() => (page ? markWikiLinks(body) : body), [page, body]);
  const components = useMemo<Components>(() => {
    const img: Components["img"] = ({ src, alt }) => {
      const path = resolveAsset(file.path, typeof src === "string" ? src : undefined);
      return path ? (
        <KnowledgeImage path={path} alt={alt} />
      ) : (
        <img
          src={typeof src === "string" ? src : undefined}
          alt={alt ?? ""}
          className="max-w-full"
        />
      );
    };
    return page
      ? {
          code,
          img,
          a: ({ href, title: hint, children }) => {
            const target = wikiTargetOf(href);
            return target === null ? (
              <a
                className="text-accent-text underline underline-offset-2"
                target="_blank"
                rel="noreferrer"
                href={href}
                title={hint}
              >
                {children}
              </a>
            ) : (
              <KnowledgeWikiLink collectionUid={collectionUid} links={file.links} target={target}>
                {children}
              </KnowledgeWikiLink>
            );
          },
        }
      : { code, img };
  }, [page, collectionUid, file.links, file.path]);

  if (source) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <CodeView value={file.body} filename={file.path} ariaLabel={file.path} fill />
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto px-8 py-7">
      <div className="mx-auto max-w-[720px]">
        <h1 className="text-xl font-bold">{title}</h1>
        <KnowledgeFileLine file={file} collectionUid={collectionUid} />
        <FindableMarkdown components={components}>{rendered}</FindableMarkdown>
      </div>
    </div>
  );
}
