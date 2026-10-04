// frontend/src/components/knowledge/KnowledgeDocumentActions.tsx
//
// The right side of a document's pane bar (boards 5.1.01, 5.1.03, 5.1.04,
// 5.1.29, 0.6.03). Reading: the Preview / Source toggle (Markdown files only),
// Edit, and the ⋯ menu — Open in editor · Reveal in Finder · (separator)
// Delete document… in danger. Editing: the unsaved state as a dot and a few
// words, then Discard and Save, whose tooltips carry Esc and ⌘S.
import { useTranslation } from "react-i18next";
import { Check, Pencil } from "lucide-react";

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
  onEdit: () => void;
  fileActions: ReturnType<typeof useFileActionItems>;
  onDelete: () => void;
}

export function ReadingActions({
  path,
  markdown,
  view,
  onView,
  onEdit,
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
      <Button variant="outline" onClick={onEdit}>
        <Pencil aria-hidden /> {t("common.edit")}
      </Button>
      <ActionMenu
        label={t("knowledge.document.more", { path })}
        actions={[
          { key: "open", label: openItem.label, onSelect: openItem.onClick },
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
