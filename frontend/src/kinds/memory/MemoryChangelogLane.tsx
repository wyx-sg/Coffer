// frontend/src/kinds/memory/MemoryChangelogLane.tsx
//
// Changelog lane of the memory store detail page: the consolidation log
// (`consolidation-log.md`) rendered read-only through the unified preview, with
// a friendly empty-state when the store has never consolidated.
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getMemoryConsolidationLog } from "./api";
import { MemorySingleDocLane } from "./MemorySingleDocLane";

export function MemoryChangelogLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["memory-consolidation-log", store],
    queryFn: () => getMemoryConsolidationLog(store),
    enabled: Boolean(store),
  });

  return (
    <MemorySingleDocLane
      title={t("memory.lanes.changelog")}
      text={q.data?.text}
      // Only offer file actions when the log exists on disk.
      path={q.data?.text ? q.data.path : undefined}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.changelog.empty")}
    />
  );
}
