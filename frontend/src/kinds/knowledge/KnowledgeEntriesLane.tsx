// frontend/src/kinds/knowledge/KnowledgeEntriesLane.tsx
//
// Notes lane of a knowledge scope: what an agent or the user wrote, one
// Markdown file each under `<scope>/notes/`. A filter box on top, the note
// tree on the left and a READ-ONLY preview on the right — the same shape as
// the Documents lane next door, over a different lane of the same scope.
//
// The filter is purely CLIENT-SIDE: it narrows the already-fetched list by
// filename/title as you type, with no request and no button. Server retrieval
// is the agents' surface (`coffer__search`) and the CLI's, not this page's.
// Humans CORRECT notes here (edit the Markdown in their editor / delete);
// agents author them through the MCP gateway.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { SearchInput } from "@/components/SearchInput";
import { translateApiError } from "@/lib/api/errors";
import {
  clearEntries,
  deleteEntry,
  listEntries,
  scopeDisplayName,
  type EntryOut,
  type ScopeOut,
} from "./api";
import { KnowledgeEntryTree } from "./KnowledgeEntryTree";
import { KnowledgeEntryViewer } from "./KnowledgeEntryViewer";
import { matchesFilter } from "./filter";

// The note list is shown as a single scrollable list, fetched in one request at
// the entries API's max page size (`le=200`) — enough for a personal scope.
const ENTRIES_FETCH_LIMIT = 200;

interface Props {
  scope: string;
  scopeResource: ScopeOut | undefined;
}

export function KnowledgeEntriesLane({ scope, scopeResource }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<EntryOut | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);

  const entriesQuery = useQuery({
    queryKey: ["knowledge-entries", scope],
    queryFn: () => listEntries(scope, ENTRIES_FETCH_LIMIT, 0),
    enabled: Boolean(scope),
  });
  const entryTotal = entriesQuery.data?.total ?? 0;

  const allEntries = entriesQuery.data?.entries ?? [];
  const visibleEntries = allEntries.filter((e) => matchesFilter(filter, e.title, e.path));
  const filtering = filter.trim().length > 0;

  // Keep the selected note in sync with the freshly-loaded list; a note the
  // filter hides drops out of the preview too.
  const liveSelected = selected ? (visibleEntries.find((e) => e.id === selected.id) ?? null) : null;

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["knowledge-entries", scope] });
    void qc.invalidateQueries({ queryKey: ["knowledge-metrics", scope] });
  };
  const del = useMutation({
    mutationFn: (id: string) => deleteEntry(scope, id),
    onSuccess: () => {
      setSelected(null);
      invalidate();
    },
  });
  const clear = useMutation({
    mutationFn: () => clearEntries(scope),
    onSuccess: () => {
      setSelected(null);
      invalidate();
    },
  });

  const scopeLabel = (scopeResource && scopeDisplayName(scopeResource)) ?? scope;

  if (entriesQuery.error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, entriesQuery.error)}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <SearchInput
          className="min-w-[16rem] max-w-sm flex-1"
          value={filter}
          onChange={setFilter}
          placeholder={t("knowledge.detail.filterPlaceholder")}
          ariaLabel={t("knowledge.detail.filterPlaceholder")}
        />
        <Button
          size="sm"
          variant="outline"
          className="shrink-0 text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
          onClick={() => setClearOpen(true)}
          disabled={clear.isPending || entryTotal === 0}
        >
          <Trash2 className="mr-1.5 size-3.5" /> {t("knowledge.detail.clearAll")}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
        <KnowledgeEntryTree
          entries={
            entriesQuery.data
              ? { entries: visibleEntries, total: visibleEntries.length }
              : undefined
          }
          selectedId={liveSelected?.id ?? null}
          isLoading={entriesQuery.isPending}
          emptyLabel={filtering ? t("knowledge.detail.noMatches") : undefined}
          total={visibleEntries.length}
          onSelect={setSelected}
        />
        <KnowledgeEntryViewer
          entry={liveSelected ?? undefined}
          isDeletePending={del.isPending}
          onDelete={() => liveSelected && setDeleteOpen(true)}
        />
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("knowledge.detail.deleteEntryTitle")}
        description={t("knowledge.detail.deleteEntryConfirm", {
          name: liveSelected?.title || "note",
        })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          if (liveSelected) del.mutate(liveSelected.id, { onSuccess: () => setDeleteOpen(false) });
        }}
      />

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title={t("knowledge.detail.clearTitle")}
        description={t("knowledge.detail.clearConfirm", { scope: scopeLabel })}
        confirmLabel={t("knowledge.detail.clearAll")}
        pending={clear.isPending}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setClearOpen(false) })}
      />
    </div>
  );
}
