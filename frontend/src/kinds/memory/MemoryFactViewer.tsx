// frontend/src/kinds/memory/MemoryFactViewer.tsx
//
// Right-hand preview/editor for the selected memory fact (mirrors the KB
// document viewer). Memory is AI-authored (agents write via the MCP `remember`
// tool); humans CORRECT existing facts — edit the Markdown body or delete it.
import { useTranslation } from "react-i18next";
import { Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/Markdown";
import type { FactOut } from "./api";

interface Props {
  fact: FactOut | undefined;
  editing: boolean;
  editText: string;
  isEditPending: boolean;
  isDeletePending: boolean;
  onStartEdit: () => void;
  onEditTextChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: () => void;
}

export function MemoryFactViewer({
  fact,
  editing,
  editText,
  isEditPending,
  isDeletePending,
  onStartEdit,
  onEditTextChange,
  onSave,
  onCancel,
  onDelete,
}: Props) {
  const { t } = useTranslation();

  if (!fact) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
        <p className="text-sm text-muted-foreground">{t("memory.detail.selectFact")}</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">{fact.name || t("memory.detail.untitled")}</span>
          <Badge variant="outline">{fact.actor}</Badge>
          {fact.type ? <Badge variant="secondary">{fact.type}</Badge> : null}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {editing ? (
            <>
              <Button size="sm" onClick={onSave} disabled={isEditPending}>
                {t("knowledgeBases.detail.save")}
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancel} disabled={isEditPending}>
                {t("knowledgeBases.detail.cancel")}
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="outline" onClick={onStartEdit}>
                <Pencil className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.edit")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                onClick={onDelete}
                disabled={isDeletePending}
              >
                <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
              </Button>
            </>
          )}
        </div>
      </div>

      {fact.description && !editing ? (
        <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
          {fact.description}
        </p>
      ) : null}

      {editing ? (
        <textarea
          value={editText}
          onChange={(e) => onEditTextChange(e.target.value)}
          className="h-[45vh] w-full resize-none border-0 bg-transparent p-4 font-mono text-sm focus:outline-none"
          spellCheck={false}
        />
      ) : (
        <div className="max-h-[50vh] overflow-auto p-4">
          <Markdown>{fact.text}</Markdown>
        </div>
      )}
    </div>
  );
}
