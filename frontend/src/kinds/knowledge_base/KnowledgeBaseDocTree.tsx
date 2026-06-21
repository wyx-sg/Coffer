// frontend/src/kinds/knowledge_base/KnowledgeBaseDocTree.tsx
//
// Left-hand document list for the KB detail page (a flat file list — KB docs
// have no folder hierarchy). Clicking a row selects it; the page renders the
// preview on the right. Page-based pagination (server offset) sits below in
// normal mode; in recall mode the page passes the hit documents directly and
// hides the pager. Rows are plain {id, title, sourceMode} so the same list
// renders both the paged documents and the search hits.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Pagination } from "@/components/Pagination";
import { cn } from "@/lib/utils";

export interface DocRow {
  id: string;
  title: string;
  /** Source mode drives the "edited" badge; absent for search-hit rows. */
  sourceMode?: string;
}

interface Props {
  items: DocRow[];
  selectedId: string | null;
  isLoading: boolean;
  total: number;
  /** 1-based current page. */
  page: number;
  pageCount: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onSelect: (documentId: string) => void;
  /** Hide the pager — used in recall mode where the list IS the hit set. */
  hidePagination?: boolean;
  /** Override the empty-state text (e.g. "no matches" in recall mode). */
  emptyLabel?: string;
}

export function KnowledgeBaseDocTree({
  items,
  selectedId,
  isLoading,
  total,
  page,
  pageCount,
  pageSize,
  onPageChange,
  onPageSizeChange,
  onSelect,
  hidePagination = false,
  emptyLabel,
}: Props) {
  const { t } = useTranslation();

  return (
    <aside className="space-y-1">
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("knowledgeBases.detail.documents")}
        <span className="ml-1 normal-case">({total})</span>
      </p>
      {isLoading ? (
        <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : total === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">
          {emptyLabel ?? t("knowledgeBases.detail.empty")}
        </p>
      ) : (
        // total > 0: render the pager even when this page is empty (e.g. the last
        // page was just emptied) so the clamp's "previous page" stays reachable.
        <>
          {items.length > 0 ? (
            <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto">
              {items.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(d.id)}
                    className={cn(
                      "flex w-full items-center gap-1.5 rounded-md py-1.5 pl-2 pr-2 text-left text-sm transition-colors",
                      selectedId === d.id
                        ? "bg-primary/10 text-primary"
                        : "hover:bg-secondary hover:text-foreground",
                    )}
                  >
                    <FileText className="size-4 shrink-0 opacity-70" />
                    <span className="min-w-0 flex-1 truncate">{d.title}</span>
                    {d.sourceMode === "edited" ? (
                      <Badge variant="outline" className="shrink-0 text-[10px]">
                        {t("knowledgeBases.sourceMode.edited", { defaultValue: "edited" })}
                      </Badge>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          {hidePagination ? null : (
            <Pagination
              page={page}
              pageCount={pageCount}
              total={total}
              pageSize={pageSize}
              onPageChange={onPageChange}
              onPageSizeChange={onPageSizeChange}
            />
          )}
        </>
      )}
    </aside>
  );
}
