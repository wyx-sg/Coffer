// frontend/src/kinds/knowledge_base/KnowledgeBaseDocTree.tsx
//
// Left-hand document list for the KB detail page (a flat file tree — KB docs
// have no folder hierarchy). Clicking a row's title selects it; the page renders
// the preview/editor on the right. The title filter is SERVER-SIDE (a `q` query
// param, lifted to props from the page hook); per-row checkboxes drive a
// multi-select bulk-delete bar scoped to the CURRENT page. Page-based pagination
// (Pagination.tsx) is rendered below the list, driven by server offset. The
// row's checkbox and its clickable title are SIBLINGS (no nested interactive
// elements) so the title stays selectable by its text for the e2e + page tests.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/Pagination";
import { BulkBar, useTableSelection } from "@/components/DataTableSelection";
import { cn } from "@/lib/utils";
import type { DocumentListOut, DocumentOut } from "./api";

interface Props {
  docs: DocumentListOut | undefined;
  selectedId: string | null;
  isLoading: boolean;
  /** Server-side title filter value (`q`), owned by the page hook. */
  filter: string;
  onFilterChange: (value: string) => void;
  /** 1-based current page. */
  page: number;
  pageCount: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
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
  filter,
  onFilterChange,
  page,
  pageCount,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  onSelect,
  onBulkDelete,
  isBulkDeletePending = false,
}: Props) {
  const { t } = useTranslation();
  // The server already applied the `q` filter; these are exactly the rows for
  // the current page.
  const items = docs?.documents ?? [];

  const [confirmOpen, setConfirmOpen] = useState(false);

  // Selection is scoped to the CURRENT PAGE so select-all + bulk actions only
  // ever touch what's on screen — mirrors DataTable's selection.
  const sel = useTableSelection<DocumentOut>(items, (d) => d.id);
  // The selection is page-scoped: drop it whenever the page changes so picks made
  // on one page never linger invisibly into another (clear is stable useCallback).
  const clearSelection = sel.clear;
  useEffect(() => clearSelection(), [page, clearSelection]);
  const visibleKeys = items.map((d) => d.id);
  const allSelected = visibleKeys.length > 0 && visibleKeys.every((k) => sel.keys.has(k));
  const someSelected = !allSelected && visibleKeys.some((k) => sel.keys.has(k));
  const selectedIds = sel.selectedRows.map((d) => d.id);

  const onConfirmBulkDelete = async () => {
    await onBulkDelete(selectedIds);
    sel.clear();
    setConfirmOpen(false);
  };

  // The filter input stays visible whenever there is a filter or any docs, so
  // the user can always clear a filter that matched nothing.
  const showFilter = Boolean(filter) || total > 0;

  return (
    <aside className="space-y-1">
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("knowledgeBases.detail.documents")}
        {docs ? <span className="ml-1 normal-case">({total})</span> : null}
      </p>
      {isLoading ? (
        <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : !showFilter ? (
        <p className="px-1 text-sm text-muted-foreground">{t("knowledgeBases.detail.empty")}</p>
      ) : (
        <>
          <Input
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
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

          {items.length === 0 ? (
            // Only a non-empty filter means "no matches"; an empty current page
            // (total > 0, page out of range) self-corrects via the clamp, so show
            // nothing there and keep the pager below reachable.
            filter ? (
              <p className="px-1 text-sm text-muted-foreground">
                {t("knowledgeBases.detail.noFilterMatches")}
              </p>
            ) : null
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
              {items.map((d) => (
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
            </ul>
          )}

          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            pageSize={pageSize}
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
          />
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
