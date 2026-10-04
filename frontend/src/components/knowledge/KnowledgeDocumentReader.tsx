// frontend/src/components/knowledge/KnowledgeDocumentReader.tsx
//
// The Document tab while reading (boards 5.1.01, 0.6.03): the document in one
// reading column, 720 wide and centred — its title, then ONE quiet line of
// properties (when it was created and by whom; a part with no data is left
// out), then the
// body. Preview renders the Markdown; Source shows the raw text in the code
// viewer. Every document is the same here, whoever wrote it last (spec
// knowledge "Let only a person delete a document"); its file actions live in
// the pane bar's ⋯ menu, not beside the text.
import { Fragment, useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { ChangeOut, FileOut } from "@/lib/api/knowledge";
import { agentLabel, writerLabel } from "@/lib/knowledge/changes";
import { withoutTitleHeading } from "@/lib/knowledge/titleHeading";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";

interface Props {
  file: FileOut;
  /** Show the raw text instead of the rendered Markdown. */
  source: boolean;
}

export function KnowledgeDocumentReader({ file, source }: Props) {
  const { t, i18n } = useTranslation();
  const history = useDocumentHistory(file.path);
  const versions = history.data?.versions;
  const body = useMemo(() => withoutTitleHeading(file.body, file.title), [file.body, file.title]);

  const oldest: ChangeOut | undefined = versions?.[versions.length - 1]?.change;

  const parts: ReactNode[] = [];
  // Created: the file's own date, else its oldest version's; by whom only when
  // a writer wrote it (an edit on disk names no one).
  const createdAt = [file.created_at, oldest?.time].find((d) => d && !Number.isNaN(Date.parse(d)));
  if (createdAt) {
    const date = new Date(createdAt).toLocaleDateString(i18n.language, {
      month: "short",
      day: "numeric",
    });
    const who =
      oldest?.writer === "disk"
        ? null
        : oldest
          ? writerLabel(t, oldest)
          : agentLabel(t, file.actor);
    parts.push(
      who
        ? t("knowledge.document.createdBy", {
            date,
            who: who === t("knowledge.writer.user") ? t("knowledge.document.you") : who,
          })
        : t("knowledge.document.created", { date }),
    );
  }

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
        <h1 className="text-xl font-bold">{file.title}</h1>
        <p className="mb-5 mt-1.5 text-xs text-text-muted">
          {parts.map((part, i) => (
            <Fragment key={i}>
              {i > 0 ? " · " : null}
              {part}
            </Fragment>
          ))}
        </p>
        <FindableMarkdown>{body}</FindableMarkdown>
      </div>
    </div>
  );
}
