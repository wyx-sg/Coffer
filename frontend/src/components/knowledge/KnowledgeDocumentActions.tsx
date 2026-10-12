// frontend/src/components/knowledge/KnowledgeDocumentActions.tsx
//
// The right side of a file's pane bar (boards 5.1.01, 0.6.03): **History**, a
// clock icon button that opens the file's history over the whole Knowledge
// area; the Preview / Source toggle (Markdown files
// only); **Open in editor** as a visible button — a file is changed in the
// person's own editor — and the ⋯ menu: Reveal in Finder · Open in Obsidian
// (only when it is installed) · (separator) Delete in danger (spec knowledge "Show a collection as one tree of read-only
// documents in the web UI").
import { useTranslation } from "react-i18next";
import { ExternalLink, History } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
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
  onHistory: () => void;
  /** Open in Obsidian, when it is installed. */
  obsidian?: MenuAction | null;
}

export function ReadingActions({
  path,
  markdown,
  view,
  onView,
  fileActions: [openItem, revealItem],
  onDelete,
  onHistory,
  obsidian = null,
}: ReadingProps) {
  const { t } = useTranslation();
  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-md"
            aria-label={t("knowledge.history.title")}
            onClick={onHistory}
          >
            <History aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{t("knowledge.history.title")}</TooltipContent>
      </Tooltip>
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
          ...(obsidian ? [obsidian] : []),
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
