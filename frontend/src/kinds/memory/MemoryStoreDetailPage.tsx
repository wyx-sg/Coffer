// frontend/src/kinds/memory/MemoryStoreDetailPage.tsx
//
// Memory store detail surface (spec 007 slice 7): a back link + header (scope +
// metric badges + Clear all), a recall box, and a Tabs shell of FIVE read-only
// lanes — Knowledge / Rules / Journal / Handoff / Changelog. Knowledge is the
// fact tree + read-only preview (recall filters it); the other lanes are
// shape-fit views over the store's curated files, all rendered through the
// unified file preview (never a hand-styled <pre>). Memory is AI-authored —
// agents write via the MCP `remember` tool; the UI is read-only for humans
// (correct a fact in your own editor / delete).
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { translateApiError } from "@/lib/api/errors";
import {
  clearFacts,
  getMemoryStore,
  getMemoryStoreMetrics,
  storeDisplayName,
  recall,
  type RecallResponse,
} from "./api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { MemoryDetailHeader } from "./MemoryDetailHeader";
import { MemoryRenameDialog } from "./MemoryRenameDialog";
import { MemoryRecallPanel } from "./MemoryRecallPanel";
import { MemoryKnowledgeLane } from "./MemoryKnowledgeLane";
import { MemoryRulesLane } from "./MemoryRulesLane";
import { MemoryJournalLane } from "./MemoryJournalLane";
import { MemoryHandoffLane } from "./MemoryHandoffLane";
import { MemoryChangelogLane } from "./MemoryChangelogLane";

export function MemoryStoreDetailPage() {
  const { t } = useTranslation();
  const store = useParams<{ name: string }>().name ?? "";
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [recallResult, setRecallResult] = useState<RecallResponse | null>(null);

  const [clearOpen, setClearOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);

  const metricsQuery = useQuery({
    queryKey: ["memory-metrics", store],
    queryFn: () => getMemoryStoreMetrics(store),
    enabled: Boolean(store),
  });
  const storeQuery = useQuery({
    queryKey: ["memory-store", store],
    queryFn: () => getMemoryStore(store),
    enabled: Boolean(store),
  });
  // Readable identity for user-facing strings: a user-set label (FR-017c), else
  // the project-dir basename (FR-017a), else the raw store name.
  const storeLabel = (storeQuery.data && storeDisplayName(storeQuery.data)) ?? store;

  const recallM = useMutation({
    mutationFn: () => recall(store, query, { topK: 5 }),
    onSuccess: (data) => setRecallResult(data),
  });
  const clear = useMutation({
    mutationFn: () => clearFacts(store),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-facts", store] });
      void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
    },
  });

  const onQueryChange = (value: string) => {
    setQuery(value);
    if (!value) setRecallResult(null); // clearing the search box exits recall mode
  };

  return (
    <div className="space-y-6 p-6">
      <MemoryDetailHeader
        store={store}
        storeResource={storeQuery.data}
        metrics={metricsQuery.data}
        isClearPending={clear.isPending}
        onClearAll={() => setClearOpen(true)}
        onRename={() => setRenameOpen(true)}
      />

      {metricsQuery.error ? (
        <p className="text-sm text-destructive" role="alert">
          {translateApiError(t, metricsQuery.error)}
        </p>
      ) : null}

      <MemoryRecallPanel
        query={query}
        error={recallM.error}
        isPending={recallM.isPending}
        onQueryChange={onQueryChange}
        onRecall={() => recallM.mutate()}
      />

      <Tabs defaultValue="knowledge">
        <TabsList>
          <TabsTrigger value="knowledge">{t("memory.detail.tabs.knowledge")}</TabsTrigger>
          <TabsTrigger value="rules">{t("memory.detail.tabs.rules")}</TabsTrigger>
          <TabsTrigger value="journal">{t("memory.detail.tabs.journal")}</TabsTrigger>
          <TabsTrigger value="handoff">{t("memory.detail.tabs.handoff")}</TabsTrigger>
          <TabsTrigger value="changelog">{t("memory.detail.tabs.changelog")}</TabsTrigger>
        </TabsList>

        <TabsContent value="knowledge" className="pt-4">
          <MemoryKnowledgeLane
            store={store}
            query={query}
            recallResult={recallResult}
            onExitRecall={() => setRecallResult(null)}
          />
        </TabsContent>
        <TabsContent value="rules" className="pt-4">
          <MemoryRulesLane store={store} />
        </TabsContent>
        <TabsContent value="journal" className="pt-4">
          <MemoryJournalLane store={store} />
        </TabsContent>
        <TabsContent value="handoff" className="pt-4">
          <MemoryHandoffLane store={store} />
        </TabsContent>
        <TabsContent value="changelog" className="pt-4">
          <MemoryChangelogLane store={store} />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title={t("memory.detail.clearTitle")}
        description={t("memory.detail.clearConfirm", { store: storeLabel })}
        confirmLabel={t("memory.detail.clearAll")}
        pending={clear.isPending}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setClearOpen(false) })}
      />

      <MemoryRenameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        store={store}
        currentLabel={storeQuery.data?.label ?? null}
      />
    </div>
  );
}
