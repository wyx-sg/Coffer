// frontend/src/kinds/knowledge_base/KnowledgeBaseDocTree.tsx
//
// Left-hand document list for the KB detail page (a flat file tree — KB docs
// have no folder hierarchy). Clicking a row selects it; the page renders the
// preview/editor on the right.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DocumentListOut } from "./api";

interface Props {
  docs: DocumentListOut | undefined;
  selectedId: string | null;
  isLoading: boolean;
  /** Fetching an additional page (the "Load more" footer is in flight). */
  isLoadingMore?: boolean;
  /** Fetch the next page; only rendered when more docs remain than are loaded. */
  onLoadMore?: () => void;
  onSelect: (documentId: string) => void;
}

export function KnowledgeBaseDocTree({
  docs,
  selectedId,
  isLoading,
  isLoadingMore = false,
  onLoadMore,
  onSelect,
}: Props) {
  const { t } = useTranslation();
  const items = docs?.documents ?? [];
  const total = docs?.total ?? items.length;
  const hasMore = items.length < total;

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
    </aside>
  );
}
