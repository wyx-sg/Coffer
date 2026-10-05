// frontend/src/components/knowledge/KnowledgeDocumentReader.tsx
//
// The open document, read-only (boards 5.1.01, 0.6.03): in one reading column,
// 720 wide and centred — its title, then ONE quiet line of properties (when it
// was created and by whom, read from its frontmatter; a part with no data is
// left out), then the body. Preview renders the Markdown; Source shows the raw
// text in the code viewer. Every document is the same here, whoever wrote it
// last (spec knowledge "Let only a person delete a document"); its file
// actions live in the pane bar, not beside the text.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import type { FileOut } from "@/lib/api/knowledge";
import { agentLabel } from "@/lib/knowledge/changes";
import { withoutTitleHeading } from "@/lib/knowledge/titleHeading";

interface Props {
  file: FileOut;
  /** Show the raw text instead of the rendered Markdown. */
  source: boolean;
}

export function KnowledgeDocumentReader({ file, source }: Props) {
  const { t, i18n } = useTranslation();
  const body = useMemo(() => withoutTitleHeading(file.body, file.title), [file.body, file.title]);

  // Created: the frontmatter's `created_at` and `actor` — nothing else records it.
  let created: string | null = null;
  if (file.created_at && !Number.isNaN(Date.parse(file.created_at))) {
    const date = new Date(file.created_at).toLocaleDateString(i18n.language, {
      month: "short",
      day: "numeric",
    });
    const who = agentLabel(t, file.actor);
    created = t("knowledge.document.createdBy", {
      date,
      who: who === t("knowledge.writer.user") ? t("knowledge.document.you") : who,
    });
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
        <p className="mb-5 mt-1.5 text-xs text-text-muted">{created}</p>
        <FindableMarkdown>{body}</FindableMarkdown>
      </div>
    </div>
  );
}
