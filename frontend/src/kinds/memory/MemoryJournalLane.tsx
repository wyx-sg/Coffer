// frontend/src/kinds/memory/MemoryJournalLane.tsx
//
// Journal lane of the memory store detail page: the period digests
// (`journal/<period>.md`, newest first) in a left list → select → the digest
// rendered read-only through the unified preview.
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getMemoryJournal } from "./api";
import { MemoryListLane, type LaneItem } from "./MemoryListLane";

export function MemoryJournalLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["memory-journal", store],
    queryFn: () => getMemoryJournal(store),
    enabled: Boolean(store),
  });

  const items: LaneItem[] = (q.data?.files ?? []).map((f) => ({
    id: f.period,
    title: f.period,
    text: f.text,
    path: f.path,
  }));

  return (
    <MemoryListLane
      listLabel={t("memory.lanes.journal")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.journal.empty")}
      selectLabel={t("memory.journal.select")}
    />
  );
}
