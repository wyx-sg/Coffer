// frontend/src/kinds/memory/MemoryListLane.tsx
//
// Shared read-only "list → preview" lane for the memory store detail page: a
// left list of files (DocRow pattern from the KB doc tree) → select → the
// selected file's Markdown rendered through the unified preview with an
// open / reveal / delete toolbar. Journal, Handoff, Rules and Changelog all
// flow through this; each maps its rows to the common item shape and passes a
// delete handler that calls the matching api.ts helper. Single-doc lanes
// (Rules/Changelog) pass exactly one item. Never a hand-styled <pre>: the body
// always flows through the frontmatter-aware <MemoryPreviewBody>.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { FileActions } from "@/components/FileActions";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { MemoryPreviewBody } from "./MemoryPreviewBody";

export interface LaneItem {
  id: string;
  /** Primary row label (e.g. a journal period or a handoff branch). */
  title: string;
  /** Optional secondary line (e.g. a relative/absolute timestamp). */
  subtitle?: string;
  text: string;
  /** Absolute on-disk path for open/reveal; omit when the lane exposes none. */
  path?: string;
}

interface Props {
  /** One-line muted intro shown above the list (per-tab purpose blurb). */
  intro: string;
  /** Header above the list ("(N)" count is appended). */
  listLabel: string;
  items: LaneItem[];
  isLoading: boolean;
  error?: unknown;
  emptyLabel: string;
  /** Placeholder shown in the right pane until a row is selected. */
  selectLabel: string;
  /** Delete the selected file; the lane wires this to its api.ts helper. */
  onDelete?: (item: LaneItem) => void;
  /** Disables the delete button while the lane's delete mutation is pending. */
  deletePending?: boolean;
}

export function MemoryListLane({
  intro,
  listLabel,
  items,
  isLoading,
  error,
  emptyLabel,
  selectLabel,
  onDelete,
  deletePending = false,
}: Props) {
  const { t } = useTranslation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const selected = items.find((i) => i.id === selectedId) ?? null;

  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="px-1 text-xs text-muted-foreground">{intro}</p>
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
              <div className="flex shrink-0 items-center gap-1.5">
                {selected.path ? <FileActions filePath={selected.path} /> : null}
                {onDelete ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => setDeleteOpen(true)}
                    disabled={deletePending}
                  >
                    <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
                  </Button>
                ) : null}
              </div>
            </div>
            <MemoryPreviewBody text={selected.text} className="max-h-[60vh] overflow-auto p-4" />
          </div>
        ) : (
          <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
            <p className="text-sm text-muted-foreground">{selectLabel}</p>
          </div>
        )}
      </div>

      {onDelete && selected ? (
        <ConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          title={t("memory.detail.deleteTitle")}
          description={t("memory.detail.deleteConfirm", { name: selected.title })}
          confirmLabel={deletePending ? t("common.deleting") : t("common.delete")}
          pending={deletePending}
          onConfirm={() => {
            onDelete(selected);
            setDeleteOpen(false);
            setSelectedId(null);
          }}
        />
      ) : null}
    </div>
  );
}
