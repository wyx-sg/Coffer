// frontend/src/kinds/memory/MemoryJournalLane.tsx
//
// Journal lane of the memory store detail page: the period digests
// (`journal/<period>.md`, newest first) in a left list → select → the digest
// rendered read-only through the unified preview, with an open/reveal/delete
// toolbar. Deleting a period also touches the consolidation log (the backend
// appends a line), so we invalidate both query keys.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { deleteJournalPeriod, getMemoryJournal } from "./api";
import { MemoryListLane, type LaneItem } from "./MemoryListLane";

export function MemoryJournalLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["memory-journal", store],
    queryFn: () => getMemoryJournal(store),
    enabled: Boolean(store),
  });

  const del = useMutation({
    mutationFn: (period: string) => deleteJournalPeriod(store, period),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory-journal", store] });
      void qc.invalidateQueries({ queryKey: ["memory-consolidation-log", store] });
    },
  });

  const items: LaneItem[] = (q.data?.files ?? []).map((f) => ({
    id: f.period,
    title: f.period,
    text: f.text,
    path: f.path,
  }));

  return (
    <MemoryListLane
      intro={t("memory.lanes.intro.journal")}
      listLabel={t("memory.lanes.journal")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.journal.empty")}
      selectLabel={t("memory.journal.select")}
      onDelete={(item) => del.mutate(item.id)}
      deletePending={del.isPending}
    />
  );
}
