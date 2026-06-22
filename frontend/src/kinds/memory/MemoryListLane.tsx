// frontend/src/kinds/memory/MemoryListLane.tsx
//
// Shared read-only "list → preview" lane for the memory store detail page: a
// left list of files (DocRow pattern from the KB doc tree) → select → the
// selected file's Markdown rendered through the unified preview with a
// FileActions bar. Journal (period digests) and Handoff (per-branch scenes)
// both flow through this; each maps its rows to the common item shape. Never a
// hand-styled <pre>: the body always flows through <FindableMarkdown>.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { FileActions } from "@/components/FileActions";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

export interface LaneItem {
  id: string;
  /** Primary row label (e.g. a journal period or a handoff branch). */
  title: string;
  /** Optional secondary line (e.g. a relative/absolute timestamp). */
  subtitle?: string;
  text: string;
  path: string;
}

interface Props {
  /** Header above the list ("(N)" count is appended). */
  listLabel: string;
  items: LaneItem[];
  isLoading: boolean;
  error?: unknown;
  emptyLabel: string;
  /** Placeholder shown in the right pane until a row is selected. */
  selectLabel: string;
}

export function MemoryListLane({
  listLabel,
  items,
  isLoading,
  error,
  emptyLabel,
  selectLabel,
}: Props) {
  const { t } = useTranslation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = items.find((i) => i.id === selectedId) ?? null;

  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
      <aside className="space-y-1">
        <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {listLabel}
          <span className="ml-1 normal-case">({items.length})</span>
        </p>
        {isLoading ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="px-1 text-sm text-muted-foreground">{emptyLabel}</p>
        ) : (
          <ul className="max-h-[60vh] space-y-0.5 overflow-y-auto">
            {items.map((i) => (
              <li key={i.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(i.id)}
                  className={cn(
                    "flex w-full items-center gap-1.5 rounded-md py-1.5 pl-2 pr-2 text-left text-sm transition-colors",
                    selectedId === i.id
                      ? "bg-primary/10 text-primary"
                      : "hover:bg-secondary hover:text-foreground",
                  )}
                >
                  <FileText className="size-4 shrink-0 opacity-70" />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate">{i.title}</span>
                    {i.subtitle ? (
                      <span className="truncate text-xs text-muted-foreground">{i.subtitle}</span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      {selected ? (
        <div className="rounded-md border border-border">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <span className="truncate font-medium">{selected.title}</span>
            <FileActions filePath={selected.path} />
          </div>
          <FindableMarkdown className="max-h-[60vh] overflow-auto p-4">
            {selected.text}
          </FindableMarkdown>
        </div>
      ) : (
        <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
          <p className="text-sm text-muted-foreground">{selectLabel}</p>
        </div>
      )}
    </div>
  );
}
