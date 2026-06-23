// frontend/src/kinds/knowledge_base/KnowledgeBaseDocTree.tsx
//
// Left-hand document list for the KB detail page (a flat file list — KB docs
// have no folder hierarchy). Clicking a row selects it; the page renders the
// preview on the right. The full list is rendered as a single scrollable list
// (no in-UI pager) — both the fetched documents (normal mode) and the deduped
// search hits (recall mode) flow through the same plain {id, title, sourceMode}
// rows.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { DocEmbedStatus } from "@/components/knowledge_base/KnowledgeBaseDocStatus";
import { cn } from "@/lib/utils";

export interface DocRow {
  id: string;
  title: string;
  /** Source mode drives the "edited" badge; absent for search-hit rows. */
  sourceMode?: string;
  /** Per-document embed status (done | embedding | queued | running | error); absent for search-hit rows. */
  embedStatus?: string | null;
}

interface Props {
  items: DocRow[];
  selectedId: string | null;
  isLoading: boolean;
  total: number;
  onSelect: (documentId: string) => void;
  /** Override the empty-state text (e.g. "no matches" in recall mode). */
  emptyLabel?: string;
}

export function KnowledgeBaseDocTree({
  items,
  selectedId,
  isLoading,
  total,
  onSelect,
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
      ) : items.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">
          {emptyLabel ?? t("knowledgeBases.detail.empty")}
        </p>
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
                <DocEmbedStatus status={d.embedStatus} />
                {d.sourceMode === "edited" ? (
                  <Badge variant="outline" className="shrink-0 text-[10px]">
                    {t("knowledgeBases.sourceMode.edited", { defaultValue: "edited" })}
                  </Badge>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
