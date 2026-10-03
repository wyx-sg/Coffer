// frontend/src/components/files/FileBody.tsx
//
// The text of a viewed file under its toolbar. Markdown reads as a document in
// one 720 column: its front matter as a key / value grid (mono key, the value
// beside it, a hairline under the grid), then the rendered body. Source — and
// every file that is not Markdown — is the line-numbered code view. A file too
// big to show says so in one line under the text.
import { useTranslation } from "react-i18next";

import { isMarkdownPath } from "@/components/files/middlePath";
import type { FileView } from "@/components/files/ViewerToolbar";
import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { splitFrontmatter } from "@/lib/preview/frontmatter";

function FrontMatterGrid({ entries }: { entries: ReturnType<typeof splitFrontmatter>["entries"] }) {
  return (
    <dl
      data-testid="front-matter"
      className="mb-5 grid grid-cols-[96px_minmax(0,1fr)] gap-x-4 gap-y-1.5 border-b border-border-subtle pb-4"
    >
      {entries.map(({ key, value }) => (
        <div key={key} className="contents">
          <dt className="font-mono text-2xs leading-[18px] text-text-subtle">{key}</dt>
          <dd className="min-w-0 whitespace-pre-wrap break-words text-xs leading-[18px] text-text">
            {Array.isArray(value) ? value.join(", ") : value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function FileBody({
  path,
  text,
  view,
  truncated,
}: {
  path: string;
  text: string;
  view: FileView;
  /** Only the start of the file was read. */
  truncated?: boolean;
}) {
  const { t } = useTranslation();
  const markdown = isMarkdownPath(path) && !truncated;
  const { entries, body } = markdown ? splitFrontmatter(text) : { entries: [], body: text };
  return (
    <>
      {markdown && view === "preview" ? (
        <div className="min-h-0 flex-1 overflow-auto px-8 py-6">
          <div className="mx-auto max-w-[720px]">
            {entries.length > 0 ? <FrontMatterGrid entries={entries} /> : null}
            <FindableMarkdown frontmatter={false}>{body}</FindableMarkdown>
          </div>
        </div>
      ) : (
        <CodeView
          value={text}
          filename={path}
          fill
          ariaLabel={path}
          className="rounded-none border-0"
        />
      )}
      {truncated ? (
        <p className="shrink-0 border-t border-border-subtle px-3 py-1.5 text-xs text-text-muted">
          {t("files.truncated")}
        </p>
      ) : null}
    </>
  );
}
