// frontend/src/components/knowledge/KnowledgeDocumentActions.tsx
//
// The right side of a file's pane bar (boards 5.1.01, 0.6.03): **History**, a
// clock icon button that opens the file's history drawer beside it and is
// pressed while the drawer is open; the Preview / Source toggle (Markdown files
// only); **Open in editor** as a visible button — a file is changed in the
// person's own editor — and the ⋯ menu: Reveal in Finder · (separator) Delete
// in danger (spec knowledge "Show a collection as one tree of read-only
// documents in the web UI").
import { useTranslation } from "react-i18next";
import { ExternalLink, History } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { useFileActionItems } from "@/lib/fileActionItems";
import { cn } from "@/lib/utils";

export type DocumentView = "preview" | "source";

interface ReadingProps {
  path: string;
  /** Preview / Source apply to Markdown only. */
  markdown: boolean;
  view: DocumentView;
  onView: (view: DocumentView) => void;
  fileActions: ReturnType<typeof useFileActionItems>;
  onDelete: () => void;
  /** The history drawer is open. */
  historyOpen: boolean;
  onHistory: () => void;
}

export function ReadingActions({
  path,
  markdown,
  view,
  onView,
  fileActions: [openItem, revealItem],
  onDelete,
  historyOpen,
  onHistory,
}: ReadingProps) {
  const { t } = useTranslation();
  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-md"
            className={cn(historyOpen && "bg-surface-selected text-text")}
            aria-label={t("knowledge.history.title")}
            aria-pressed={historyOpen}
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
