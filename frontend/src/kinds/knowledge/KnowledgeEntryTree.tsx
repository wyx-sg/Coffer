// frontend/src/kinds/knowledge/KnowledgeEntryTree.tsx
//
// Left-hand entry list for the Entries lane (mirrors the document tree next
// door — same shape, different lane of the same scope). Each entry is one .md
// file on disk; clicking selects it for the preview on the right. The full list
// is rendered as a single scrollable list (no in-UI pager). The tree has NO
// filter and NO multi-select.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { cn } from "@/lib/utils";
import type { EntryListOut, EntryOut } from "./api";

interface Props {
  entries: EntryListOut | undefined;
  selectedId: string | null;
  isLoading: boolean;
  total: number;
  onSelect: (entry: EntryOut) => void;
  /** Override the empty-state text (e.g. "no matches" in recall mode). */
  emptyLabel?: string;
}

export function KnowledgeEntryTree({
  entries,
  selectedId,
  isLoading,
  total,
  onSelect,
  emptyLabel,
}: Props) {
  const { t } = useTranslation();
  const items = entries?.entries ?? [];

  return (
    <aside className="space-y-1">
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("knowledge.detail.entries")}
        {entries ? <span className="ml-1 normal-case">({total})</span> : null}
      </p>
      {isLoading ? (
        <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">
          {emptyLabel ?? t("knowledge.detail.emptyEntries")}
        </p>
      ) : (
        <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto">
          {items.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => onSelect(e)}
                className={cn(
                  "flex w-full items-center gap-1.5 rounded-md py-1.5 pl-2 pr-2 text-left text-sm transition-colors",
                  selectedId === e.id
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-secondary hover:text-foreground",
                )}
              >
                <FileText className="size-4 shrink-0 opacity-70" />
                <span className="min-w-0 flex-1 truncate">{e.title || e.text.slice(0, 40)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
