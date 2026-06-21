// frontend/src/kinds/knowledge_base/KnowledgeBaseDocTree.tsx
//
// Left-hand document list for the KB detail page (a flat file tree — KB docs
// have no folder hierarchy). Clicking a row's title selects it; the page renders
// the preview/editor on the right. A small filter input narrows a long list by
// title, and per-row checkboxes drive a multi-select bulk-delete bar. The row's
// checkbox and its clickable title are SIBLINGS (no nested interactive elements)
// so the title stays selectable by its text for the e2e + page tests.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { BulkBar, useTableSelection } from "@/components/DataTableSelection";
import { cn } from "@/lib/utils";
import type { DocumentListOut, DocumentOut } from "./api";

interface Props {
  docs: DocumentListOut | undefined;
  selectedId: string | null;
  isLoading: boolean;
  /** Fetching an additional page (the "Load more" footer is in flight). */
  isLoadingMore?: boolean;
  /** Fetch the next page; only rendered when more docs remain than are loaded. */
  onLoadMore?: () => void;
  onSelect: (documentId: string) => void;
  /** Bulk-delete the given document ids (fan-out lives in the page hook). */
  onBulkDelete: (documentIds: string[]) => void | Promise<void>;
  /** True while the bulk-delete fan-out is in flight. */
  isBulkDeletePending?: boolean;
}

export function KnowledgeBaseDocTree({
  docs,
  selectedId,
  isLoading,
  isLoadingMore = false,
  onLoadMore,
  onSelect,
  onBulkDelete,
  isBulkDeletePending = false,
}: Props) {
  const { t } = useTranslation();
  const items = useMemo(() => docs?.documents ?? [], [docs]);
  const total = docs?.total ?? items.length;
  const hasMore = items.length < total;

  const [filter, setFilter] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Client-side title filter (case-insensitive substring); empty → all docs.
  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return items;
    return items.filter((d) => d.title.toLowerCase().includes(q));
  }, [items, filter]);

  // Selection is scoped to the FILTERED (visible) set so select-all + bulk
  // actions only ever touch what's on screen — mirrors DataTable's selection.
  const sel = useTableSelection<DocumentOut>(visible, (d) => d.id);
  const visibleKeys = visible.map((d) => d.id);
  const allSelected = visibleKeys.length > 0 && visibleKeys.every((k) => sel.keys.has(k));
  const someSelected = !allSelected && visibleKeys.some((k) => sel.keys.has(k));
  const selectedIds = sel.selectedRows.map((d) => d.id);

  const onConfirmBulkDelete = async () => {
    await onBulkDelete(selectedIds);
    sel.clear();
    setConfirmOpen(false);
  };

  return (
    <aside className="space-y-1">
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("knowledgeBases.detail.documents")}
        {docs ? <span className="ml-1 normal-case">({docs.total})</span> : null}
      </p>
      {isLoading ? (
        <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">{t("knowledgeBases.detail.empty")}</p>
      ) : (
        <>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("knowledgeBases.detail.filterDocs")}
            aria-label={t("knowledgeBases.detail.filterDocs")}
            className="h-8 text-sm"
          />

          {sel.selectedRows.length > 0 ? (
            <BulkBar
              label={t("common.bulk.selected", { count: sel.selectedRows.length })}
              clearLabel={t("common.clear")}
              onClear={sel.clear}
            >
              <Button
                size="sm"
                variant="outline"
                disabled={isBulkDeletePending}
                className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setConfirmOpen(true)}
              >
                {isBulkDeletePending ? t("common.deleting") : t("common.delete")}
              </Button>
            </BulkBar>
          ) : null}

          {visible.length === 0 ? (
            <p className="px-1 text-sm text-muted-foreground">
              {t("knowledgeBases.detail.noFilterMatches")}
            </p>
          ) : (
            <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto">
              <li className="flex items-center gap-2 px-2 py-1">
                <Checkbox
                  checked={allSelected}
                  indeterminate={someSelected}
                  aria-label={t("common.bulk.selectAll")}
                  onChange={() => sel.setMany(visibleKeys, !allSelected)}
                />
                <span className="text-xs text-muted-foreground">{t("common.bulk.selectAll")}</span>
              </li>
              {visible.map((d) => (
                <li key={d.id} className="flex items-center gap-1.5">
                  <Checkbox
                    checked={sel.keys.has(d.id)}
                    aria-label={t("common.bulk.selectRow")}
                    onChange={() => sel.toggle(d.id)}
                  />
                  <button
                    type="button"
                    onClick={() => onSelect(d.id)}
                    className={cn(
                      "flex min-w-0 flex-1 items-center gap-1.5 rounded-md py-1.5 pl-2 pr-2 text-left text-sm transition-colors",
                      selectedId === d.id
                        ? "bg-primary/10 text-primary"
                        : "hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    <FileText className="size-4 shrink-0 opacity-70" />
                    <span className="min-w-0 flex-1 truncate">{d.title}</span>
                    {d.source_mode === "edited" ? (
                      <Badge variant="outline" className="shrink-0 text-[10px]">
                        {t("knowledgeBases.sourceMode.edited", { defaultValue: "edited" })}
                      </Badge>
                    ) : null}
                  </button>
                </li>
              ))}
              {hasMore && onLoadMore ? (
                <li>
                  <button
                    type="button"
                    onClick={onLoadMore}
                    disabled={isLoadingMore}
                    className="mt-1 w-full rounded-md py-1.5 text-center text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
                  >
                    {isLoadingMore
                      ? t("common.loading")
                      : t("common.loadMore", { loaded: items.length, total })}
                  </button>
                </li>
              ) : null}
            </ul>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("knowledgeBases.detail.bulkDeleteConfirm", { count: selectedIds.length })}
        confirmLabel={isBulkDeletePending ? t("common.deleting") : t("common.delete")}
        pending={isBulkDeletePending}
        onConfirm={onConfirmBulkDelete}
      />
    </aside>
  );
}
