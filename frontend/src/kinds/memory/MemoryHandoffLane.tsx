// frontend/src/kinds/memory/MemoryHandoffLane.tsx
//
// Handoff lane of the memory store detail page: the per-branch scene notes
// (`handoff/<branch-slug>.md`) in a left list (branch + last-updated) → select
// → the scene rendered read-only through the unified preview, with an
// open/reveal/delete toolbar. Deleting a scene also touches the consolidation
// log (the backend appends a line), so we invalidate both query keys.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { formatDateTime } from "@/lib/utils";
import { deleteHandoffBranch, getMemoryHandoff } from "./api";
import { MemoryListLane, type LaneItem } from "./MemoryListLane";

export function MemoryHandoffLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["memory-handoff", store],
    queryFn: () => getMemoryHandoff(store),
    enabled: Boolean(store),
  });

  const del = useMutation({
    mutationFn: (branch: string) => deleteHandoffBranch(store, branch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-handoff", store] });
      void qc.invalidateQueries({ queryKey: ["memory-consolidation-log", store] });
    },
  });

  const items: LaneItem[] = (q.data?.scenes ?? []).map((s) => ({
    id: s.branch,
    title: s.branch,
    subtitle: t("memory.handoff.updatedAt", { time: formatDateTime(s.updated_at) }),
    text: s.text,
    path: s.path,
  }));

  return (
    <MemoryListLane
      intro={t("memory.lanes.intro.handoff")}
      listLabel={t("memory.lanes.handoff")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.handoff.empty")}
      selectLabel={t("memory.handoff.select")}
      onDelete={(item) => del.mutate(item.id)}
      deletePending={del.isPending}
    />
  );
}
