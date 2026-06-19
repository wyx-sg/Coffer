// frontend/src/components/knowledge/KnowledgeItemViewer.tsx
// Read-only viewer for the selected knowledge item — a note OR a document. It
// renders the Markdown read-only (NO in-app editor, per FR-020 / FR-021) and
// keeps the external-editor / reveal / copy-path affordances via <FileActions>,
// plus the KB lock badge for documents. A note's body rides on the item; a
// document's body is fetched lazily (the list carries metadata only).
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FileText, Lock, StickyNote, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileActions } from "@/components/FileActions";
import { Markdown } from "@/components/Markdown";
import { getDocument } from "@/kinds/knowledge_base/api";
import type { KnowledgeItem } from "@/lib/api/knowledge";

interface Props {
  item: KnowledgeItem;
  /** True while a delete (note removal / document soft-delete) is in flight. */
  isDeletePending: boolean;
  onDelete: () => void;
  onClose: () => void;
}

export function KnowledgeItemViewer({ item, isDeletePending, onDelete, onClose }: Props) {
  const { t } = useTranslation();

  const docQuery = useQuery({
    queryKey: ["knowledge", "doc", item.kbName, item.documentId],
    queryFn: () => getDocument(item.kbName!, item.documentId!),
    enabled: item.type === "document" && Boolean(item.kbName && item.documentId),
  });

  const Icon = item.type === "note" ? StickyNote : FileText;
  const body = item.type === "note" ? (item.noteBody ?? "") : (docQuery.data?.markdown ?? "");
  const path = item.type === "note" ? item.path : (docQuery.data?.path ?? item.path);
  const folderPath =
    item.type === "note" ? item.folderPath : (docQuery.data?.folder_path ?? item.folderPath);
  const loading = item.type === "document" && docQuery.isPending;

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate font-medium">{item.title || t("knowledge.untitled")}</span>
          <Badge variant="secondary" className="rounded-sm">
            {t(`knowledge.type.${item.type}`)}
          </Badge>
          {item.type === "note" && item.noteType ? (
            <Badge variant="outline">{item.noteType}</Badge>
          ) : null}
          {item.locked ? (
            <Badge variant="outline" className="gap-1 text-status-warn">
              <Lock className="size-3" /> {t("knowledge.viewer.locked")}
            </Badge>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {path ? <FileActions filePath={path} folderPath={folderPath} /> : null}
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            onClick={onDelete}
            disabled={isDeletePending || item.locked}
            title={item.type === "document" ? t("knowledge.viewer.deleteDocHint") : undefined}
          >
            <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onClose}
            aria-label={t("knowledge.viewer.close")}
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      <div className="max-h-[60vh] overflow-auto p-4">
        {loading ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : (
          <Markdown>{body}</Markdown>
        )}
      </div>
    </div>
  );
}
