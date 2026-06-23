// frontend/src/kinds/memory/MemoryFactTree.tsx
//
// Left-hand fact list for the memory store detail page (mirrors the KB document
// tree). Each fact is one .md file on disk; clicking selects it for the
// preview/editor on the right. The full list is rendered as a single scrollable
// list (no in-UI pager). The tree has NO filter and NO multi-select.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FactListOut, FactOut } from "./api";

interface Props {
  facts: FactListOut | undefined;
  selectedId: string | null;
  isLoading: boolean;
  total: number;
  onSelect: (fact: FactOut) => void;
  /** Override the empty-state text (e.g. "no matches" in recall mode). */
  emptyLabel?: string;
}

export function MemoryFactTree({
  facts,
  selectedId,
  isLoading,
  total,
  onSelect,
  emptyLabel,
}: Props) {
  const { t } = useTranslation();
  const items = facts?.facts ?? [];

  return (
    <aside className="space-y-1">
      <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("memory.detail.facts")}
        {facts ? <span className="ml-1 normal-case">({total})</span> : null}
      </p>
      {isLoading ? (
        <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">
          {emptyLabel ?? t("memory.detail.empty")}
        </p>
      ) : (
        <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto">
          {items.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                onClick={() => onSelect(f)}
                className={cn(
                  "flex w-full items-center gap-1.5 rounded-md py-1.5 pl-2 pr-2 text-left text-sm transition-colors",
                  selectedId === f.id
                    ? "bg-primary/10 text-primary"
                    : "hover:bg-secondary hover:text-foreground",
                )}
              >
                <FileText className="size-4 shrink-0 opacity-70" />
                <span className="min-w-0 flex-1 truncate">{f.title || f.text.slice(0, 40)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
