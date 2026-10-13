// frontend/src/components/knowledge/KnowledgeDocumentReader.tsx
//
// The open file, read-only (boards 5.1.01, 0.6.03): in one reading column,
// 720 wide and centred — its title (the body's own leading `# Heading` when it
// has one, so the page never shows two), then ONE quiet line of what it is
// (KnowledgeFileLine: a page's type and sources, a source's citing pages or
// Waiting mark, who created it and when), then the body.
// Preview renders the Markdown — its own HTML sanitised — and every link
// opens where it points (KnowledgeLink): a `[[link]]` or a relative path the
// file it names, a web link the browser. A source that still carries an
// export's own frontmatter or Confluence storage markers is shown the way an
// import reads it now (`readable_body`), with a note that the file itself is
// unchanged; Source shows the raw text in the code viewer. A picture the Markdown links by a relative path (an upload's,
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
import { useTranslation } from "react-i18next";

import { KnowledgeFileLine } from "@/components/knowledge/KnowledgeFileLine";
import { KnowledgeImage } from "@/components/knowledge/KnowledgeImage";
import { KnowledgeLink } from "@/components/knowledge/KnowledgeLink";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { FileOut } from "@/lib/api/knowledge";
import { resolveAsset } from "@/lib/knowledge/assets";
import { splitTitleHeading } from "@/lib/knowledge/titleHeading";
import { markWikiLinks } from "@/lib/knowledge/wikiLinks";

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
  const { t } = useTranslation();
  const readable = file.readable_body ?? null;
  const { title, body } = useMemo(
    () => splitTitleHeading(readable ?? file.body, file.title),
    [readable, file.body, file.title],
  );
  // A page's or a note's `[[links]]`; a source is material, linked as written.
  const wiki = file.kind !== "source";
  const rendered = useMemo(() => (wiki ? markWikiLinks(body) : body), [wiki, body]);
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
    return {
      code,
      img,
      a: ({ href, title: hint, children }) => (
        <KnowledgeLink
          href={typeof href === "string" ? href : undefined}
          title={hint}
          documentPath={file.path}
          links={file.links}
          collectionUid={collectionUid}
        >
          {children}
        </KnowledgeLink>
      ),
    };
  }, [collectionUid, file.links, file.path]);

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
        {readable !== null ? (
          <p
            data-testid="readable-body-note"
            className="mb-4 rounded-md bg-surface-sunken px-3 py-2 text-xs text-text-muted"
          >
            {t("knowledge.document.readableNote")}
          </p>
        ) : null}
        <FindableMarkdown components={components} html>
          {rendered}
        </FindableMarkdown>
      </div>
    </div>
  );
}
