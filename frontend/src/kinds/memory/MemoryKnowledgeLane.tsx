// frontend/src/kinds/memory/MemoryKnowledgeLane.tsx
//
// Knowledge lane of the memory store detail page: the fact TREE on the left and
// a READ-ONLY preview on the right (mirrors the KB detail page). This is the
// original flat-fact surface, now one of the store's five lanes. Recall (driven
// by the panel above the tabs) filters this lane to the matched facts and opens
// the top hit highlighted; clearing the search returns to the full list. Humans
// CORRECT facts here (edit the Markdown in their editor / delete) — agents
// author them via the MCP `remember` tool.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import {
  deleteFact,
  getFact,
  listFacts,
  type FactOut,
  type RecallResponse,
} from "./api";
import { MemoryFactTree } from "./MemoryFactTree";
import { MemoryFactViewer } from "./MemoryFactViewer";

// The fact list is shown as a single scrollable list, fetched in one request at
// the facts API's max page size (`le=200`) — enough for a personal store.
const FACTS_FETCH_LIMIT = 200;

interface Props {
  store: string;
  /** Active recall query (highlighted in the viewer; "" = full-list mode). */
  query: string;
  /** Recall hits, or null when not in recall mode. */
  recallResult: RecallResponse | null;
  /** A delete returns to the full list — clears stale recall state. */
  onExitRecall: () => void;
}

export function MemoryKnowledgeLane({ store, query, recallResult, onExitRecall }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [selected, setSelected] = useState<FactOut | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const factsQuery = useQuery({
    queryKey: ["memory-facts", store],
    queryFn: () => listFacts(store, FACTS_FETCH_LIMIT, 0),
    enabled: Boolean(store),
  });
  const factTotal = factsQuery.data?.total ?? 0;

  // --- recall mode -----------------------------------------------------------
  const recalling = recallResult !== null;
  const hitIds = recallResult ? [...new Set(recallResult.hits.map((h) => h.id))] : [];
  // Recall returns only ranked snippets; fetch the full facts so the rows
  // (name + actor badge) and the viewer (full body) render like normal mode.
  const recallFactsQuery = useQuery({
    queryKey: ["memory-recall-facts", store, hitIds],
    queryFn: async () => {
      const facts = await Promise.all(hitIds.map((id) => getFact(store, id).catch(() => null)));
      return facts.filter((f): f is FactOut => f !== null);
    },
    enabled: recalling && hitIds.length > 0,
  });
  const recallFacts = recallFactsQuery.data ?? [];
  const recallLoading = recalling && hitIds.length > 0 && recallFactsQuery.isPending;
  // Auto-select the top hit when a recall resolves so its match opens highlighted.
  useEffect(() => {
    const facts = recallFactsQuery.data;
    if (recalling && facts && facts.length > 0) setSelected(facts[0]);
  }, [recallFactsQuery.data, recalling]);

  // Keep the selected fact in sync with the freshly-loaded list when it's on the
  // current page; otherwise keep showing the captured selection.
  const sourceFacts = recalling ? recallFacts : (factsQuery.data?.facts ?? []);
  const liveSelected = selected
    ? (sourceFacts.find((f) => f.id === selected.id) ?? selected)
    : null;

  const del = useMutation({
    mutationFn: (id: string) => deleteFact(store, id),
    onSuccess: () => {
      setSelected(null);
      onExitRecall(); // a delete returns to the full list (no stale hit rows)
      void qc.invalidateQueries({ queryKey: ["memory-facts", store] });
      void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
    },
  });

  if (factsQuery.error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, factsQuery.error)}
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(220px,300px)_1fr]">
      <MemoryFactTree
        facts={recalling ? { facts: recallFacts, total: recallFacts.length } : factsQuery.data}
        selectedId={liveSelected?.id ?? null}
        isLoading={recalling ? recallLoading : factsQuery.isPending}
        emptyLabel={recalling ? t("memory.detail.noMatches") : undefined}
        total={recalling ? recallFacts.length : factTotal}
        onSelect={setSelected}
      />
      <MemoryFactViewer
        fact={liveSelected ?? undefined}
        initialQuery={recalling ? query : ""}
        isDeletePending={del.isPending}
        onDelete={() => liveSelected && setDeleteOpen(true)}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("memory.detail.deleteTitle")}
        description={t("memory.detail.deleteConfirm", { name: liveSelected?.name || "fact" })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          if (liveSelected) {
            del.mutate(liveSelected.id, { onSuccess: () => setDeleteOpen(false) });
          }
        }}
      />
    </div>
  );
}
