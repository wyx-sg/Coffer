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
  onSelect: (documentId: string) => void;
}

export function KnowledgeBaseDocTree({ docs, selectedId, isLoading, onSelect }: Props) {
  const { t } = useTranslation();
  const items = docs?.documents ?? [];

  return (
    <aside className="rounded-md border border-border">
      <div className="border-b border-border px-3 py-2 text-sm font-medium">
        {t("knowledgeBases.detail.documents")}
        {docs ? <span className="ml-1 text-muted-foreground">({docs.total})</span> : null}
      </div>
      {isLoading ? (
        <p className="px-3 py-3 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <p className="px-3 py-3 text-sm text-muted-foreground">
          {t("knowledgeBases.detail.empty")}
        </p>
      ) : (
        <ul className="max-h-[60vh] overflow-y-auto py-1">
          {items.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                onClick={() => onSelect(d.id)}
                className={cn(
                  "flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-secondary",
                  selectedId === d.id && "bg-secondary",
                )}
              >
                <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{d.title}</span>
                  <Badge variant="outline" className="mt-0.5 text-[10px]">
                    {t(`knowledgeBases.sourceMode.${d.source_mode}`, {
                      defaultValue: d.source_mode,
                    })}
                  </Badge>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
