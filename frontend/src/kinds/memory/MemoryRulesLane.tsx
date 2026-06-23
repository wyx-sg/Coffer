// frontend/src/kinds/memory/MemoryRulesLane.tsx
//
// Rules lane of the memory store detail page: a single curated doc, now shown
// through the shared file-tree lane as one file row (so every tab shares the
// "tree → preview" layout). Empty store → no items → the lane's friendly
// empty-state. Deleting clears the rules file; the backend appends a line to
// the consolidation log, so both query keys are invalidated.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { deleteMemoryRules, getMemoryRules } from "./api";
import { MemoryListLane, type LaneItem } from "./MemoryListLane";

export function MemoryRulesLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["memory-rules", store],
    queryFn: () => getMemoryRules(store),
    enabled: Boolean(store),
  });

  const del = useMutation({
    mutationFn: () => deleteMemoryRules(store),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-rules", store] });
      void qc.invalidateQueries({ queryKey: ["memory-consolidation-log", store] });
    },
  });

  // One curated doc → one row; absent (no text) → no items → empty-state.
  const items: LaneItem[] = q.data?.text
    ? [{ id: "rules", title: t("memory.lanes.rules"), text: q.data.text }]
    : [];

  return (
    <MemoryListLane
      intro={t("memory.lanes.intro.rules")}
      listLabel={t("memory.lanes.rules")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.rules.empty")}
      selectLabel={t("memory.rules.select")}
      onDelete={() => del.mutate()}
      deletePending={del.isPending}
    />
  );
}
