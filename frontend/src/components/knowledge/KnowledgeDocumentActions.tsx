// frontend/src/components/knowledge/KnowledgeDocumentActions.tsx
//
// The right side of a document's pane bar (boards 5.1.01, 0.6.03): the
// Preview / Source toggle (Markdown files only), **Open in editor** as a
// visible button — a document is changed in the person's own editor — and the
// ⋯ menu: Reveal in Finder · History… · (separator) Delete document in danger
// (spec knowledge "Show a collection as one tree of read-only documents in the
// web UI").
//
// `EditingActions` is the editing bar Memory's note pane still draws.
import { useTranslation } from "react-i18next";
import { Check, ExternalLink } from "lucide-react";

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
  onHistory: () => void;
  onDelete: () => void;
}

export function ReadingActions({
  path,
  markdown,
  view,
  onView,
  fileActions: [openItem, revealItem],
  onHistory,
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
          { key: "history", label: t("knowledge.document.history"), onSelect: onHistory },
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

interface EditingProps {
  dirty: boolean;
  /** The save was refused as stale — the text is not saved and cannot be yet. */
  notSaved: boolean;
  saving: boolean;
  onDiscard: () => void;
  onSave: () => void;
  /** Only the state, no buttons — Compare carries its own footer. */
  statusOnly?: boolean;
}

export function EditingActions({
  dirty,
  notSaved,
  saving,
  onDiscard,
  onSave,
  statusOnly,
}: EditingProps) {
  const { t } = useTranslation();
  const status = notSaved
    ? { label: t("knowledge.editor.notSaved"), dot: "bg-danger" }
    : dirty
      ? { label: t("knowledge.editor.unsaved"), dot: "bg-warning" }
      : null;
  return (
    <>
      {status ? (
        <span className="mr-1 inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
          <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", status.dot)} />
          {status.label}
        </span>
      ) : null}
      {statusOnly ? null : (
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" onClick={onDiscard} disabled={saving}>
                {t("knowledge.editor.discard")}
              </Button>
            </TooltipTrigger>
            <TooltipContent shortcut="Esc">{t("knowledge.editor.discard")}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button onClick={onSave} disabled={!dirty || saving || notSaved}>
                <Check aria-hidden /> {saving ? t("common.saving") : t("common.save")}
              </Button>
            </TooltipTrigger>
            <TooltipContent shortcut="⌘S">{t("common.save")}</TooltipContent>
          </Tooltip>
        </>
      )}
    </>
  );
}
