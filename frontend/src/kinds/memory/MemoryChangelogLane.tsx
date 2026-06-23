// frontend/src/kinds/memory/MemoryChangelogLane.tsx
//
// Changelog lane of the memory store detail page: the consolidation log
// (`consolidation-log.md`), now shown through the shared file-tree lane as one
// file row (so every tab shares the "tree → preview" layout). Empty store → no
// items → the lane's friendly empty-state. Deleting the log does NOT self-append
// a changelog line, so only its own query key is invalidated.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { deleteConsolidationLog, getMemoryConsolidationLog } from "./api";
import { MemoryListLane, type LaneItem } from "./MemoryListLane";

export function MemoryChangelogLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["memory-consolidation-log", store],
    queryFn: () => getMemoryConsolidationLog(store),
    enabled: Boolean(store),
  });

  const del = useMutation({
    mutationFn: () => deleteConsolidationLog(store),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-consolidation-log", store] });
    },
  });

  // The log is one doc → one row (with its on-disk path); absent → empty-state.
  const items: LaneItem[] = q.data?.text
    ? [{ id: "changelog", title: t("memory.lanes.changelog"), text: q.data.text, path: q.data.path }]
    : [];

  return (
    <MemoryListLane
      intro={t("memory.lanes.intro.changelog")}
      listLabel={t("memory.lanes.changelog")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.changelog.empty")}
      selectLabel={t("memory.changelog.select")}
      onDelete={() => del.mutate()}
      deletePending={del.isPending}
    />
  );
}
