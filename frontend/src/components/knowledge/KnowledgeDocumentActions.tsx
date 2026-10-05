// frontend/src/components/knowledge/KnowledgeDocumentActions.tsx
//
// The right side of a document's pane bar (boards 5.1.01, 0.6.03): the
// Preview / Source toggle (Markdown files only), **Open in editor** as a
// visible button — a document is changed in the person's own editor — and the
// ⋯ menu: Reveal in Finder · (separator) Delete document in danger. The
// document's history is its History tab, beside the crumbs
// (spec knowledge "Show a collection as one tree of read-only documents in the
// web UI").
//
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { Segmented } from "@/components/ui/segmented";
import type { useFileActionItems } from "@/lib/fileActionItems";

export type DocumentView = "preview" | "source";

interface ReadingProps {
  path: string;
  /** Preview / Source apply to Markdown only. */
  markdown: boolean;
  view: DocumentView;
  onView: (view: DocumentView) => void;
  fileActions: ReturnType<typeof useFileActionItems>;
  onDelete: () => void;
}

export function ReadingActions({
  path,
  markdown,
  view,
  onView,
  fileActions: [openItem, revealItem],
  onDelete,
}: ReadingProps) {
  const { t } = useTranslation();
  return (
    <>
      {markdown ? (
        <Segmented
          label={t("knowledge.document.view")}
          value={view}
          onChange={onView}
          options={[
            { value: "preview", label: t("knowledge.document.preview") },
            { value: "source", label: t("knowledge.document.source") },
          ]}
        />
      ) : null}
      <Button variant="outline" onClick={openItem.onClick}>
        <ExternalLink aria-hidden /> {openItem.label}
      </Button>
      <ActionMenu
        label={t("knowledge.document.more", { path })}
        actions={[
          { key: "reveal", label: revealItem.label, onSelect: revealItem.onClick },
          {
            key: "delete",
            label: t("knowledge.deleteDocument.menu"),
            destructive: true,
            separated: true,
            onSelect: onDelete,
          },
        ]}
      />
    </>
  );
}
