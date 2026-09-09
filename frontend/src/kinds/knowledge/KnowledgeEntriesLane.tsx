// frontend/src/kinds/knowledge/KnowledgeEntriesLane.tsx
//
// Entries lane of a knowledge scope: what an agent wrote with `coffer__write`,
// one Markdown file each under `<scope>/knowledge/`. A recall bar on top, the
// entry tree on the left and a READ-ONLY preview on the right — the same shape
// as the Documents lane next door, over a different lane of the same scope.
// Recall filters the lane to the matched entries and opens the top hit
// highlighted; clearing the box returns to the full list. Humans CORRECT
// entries here (edit the Markdown in their editor / delete); agents author them
// through the MCP gateway.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import {
  clearEntries,
  deleteEntry,
  getEntry,
  listEntries,
  recall,
  scopeDisplayName,
  type EntryOut,
  type RecallResponse,
  type ScopeOut,
} from "./api";
import { KnowledgeEntryTree } from "./KnowledgeEntryTree";
import { KnowledgeEntryViewer } from "./KnowledgeEntryViewer";
import { KnowledgeSearchBar } from "./KnowledgeSearchBar";

// The entry list is shown as a single scrollable list, fetched in one request at
// the entries API's max page size (`le=200`) — enough for a personal scope.
const ENTRIES_FETCH_LIMIT = 200;

interface Props {
  scope: string;
  scopeResource: ScopeOut | undefined;
}

export function KnowledgeEntriesLane({ scope, scopeResource }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [recallResult, setRecallResult] = useState<RecallResponse | null>(null);
  const [selected, setSelected] = useState<EntryOut | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);

  const entriesQuery = useQuery({
    queryKey: ["knowledge-entries", scope],
    queryFn: () => listEntries(scope, ENTRIES_FETCH_LIMIT, 0),
    enabled: Boolean(scope),
  });
  const entryTotal = entriesQuery.data?.total ?? 0;

  const recallM = useMutation({
    mutationFn: () => recall(scope, query, { topK: 5 }),
    onSuccess: (data) => setRecallResult(data),
  });
  const onQueryChange = (value: string) => {
    setQuery(value);
    if (!value) setRecallResult(null); // clearing the box exits recall mode
  };

  // --- recall mode -----------------------------------------------------------
  const recalling = recallResult !== null;
  const hitIds = recallResult ? [...new Set(recallResult.hits.map((h) => h.id))] : [];
  // Recall returns only ranked snippets; fetch the full entries so the rows
  // (title) and the viewer (full body) render like normal mode.
  const recallEntriesQuery = useQuery({
    queryKey: ["knowledge-recall-entries", scope, hitIds],
    queryFn: async () => {
      const rows = await Promise.all(hitIds.map((id) => getEntry(scope, id).catch(() => null)));
      return rows.filter((e): e is EntryOut => e !== null);
    },
    enabled: recalling && hitIds.length > 0,
  });
  const recallEntries = recallEntriesQuery.data ?? [];
  const recallLoading = recalling && hitIds.length > 0 && recallEntriesQuery.isPending;
  // Auto-select the top hit when a recall resolves so its match opens highlighted.
  useEffect(() => {
    const rows = recallEntriesQuery.data;
    if (recalling && rows && rows.length > 0) setSelected(rows[0]);
  }, [recallEntriesQuery.data, recalling]);

  // Keep the selected entry in sync with the freshly-loaded list when it's on
  // the current page; otherwise keep showing the captured selection.
  const sourceEntries = recalling ? recallEntries : (entriesQuery.data?.entries ?? []);
  const liveSelected = selected
    ? (sourceEntries.find((e) => e.id === selected.id) ?? selected)
    : null;

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["knowledge-entries", scope] });
    void qc.invalidateQueries({ queryKey: ["knowledge-metrics", scope] });
  };
  const del = useMutation({
    mutationFn: (id: string) => deleteEntry(scope, id),
    onSuccess: () => {
      setSelected(null);
      setRecallResult(null); // a delete returns to the full list (no stale hits)
      invalidate();
    },
  });
  const clear = useMutation({
    mutationFn: () => clearEntries(scope),
    onSuccess: () => {
      setSelected(null);
      setRecallResult(null);
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
      <KnowledgeSearchBar
        query={query}
        error={recallM.error}
        isPending={recallM.isPending}
        onQueryChange={onQueryChange}
        onSearch={() => recallM.mutate()}
        placeholder={t("knowledge.detail.recallPlaceholder")}
        actionLabel={t("knowledge.detail.recall")}
      />

      <div className="flex items-center justify-between gap-2">
        <p className="px-1 text-xs text-muted-foreground">{t("knowledge.lanes.intro.entries")}</p>
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
            recalling ? { entries: recallEntries, total: recallEntries.length } : entriesQuery.data
          }
          selectedId={liveSelected?.id ?? null}
          isLoading={recalling ? recallLoading : entriesQuery.isPending}
          emptyLabel={recalling ? t("knowledge.detail.noMatches") : undefined}
          total={recalling ? recallEntries.length : entryTotal}
          onSelect={setSelected}
        />
        <KnowledgeEntryViewer
          entry={liveSelected ?? undefined}
          initialQuery={recalling ? query : ""}
          isDeletePending={del.isPending}
          onDelete={() => liveSelected && setDeleteOpen(true)}
        />
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("knowledge.detail.deleteEntryTitle")}
        description={t("knowledge.detail.deleteEntryConfirm", {
          name: liveSelected?.title || "entry",
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
