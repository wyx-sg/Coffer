// frontend/src/kinds/memory/MemoryRulesLane.tsx
//
// Rules lane of the memory store detail page: a single curated doc rendered
// read-only through the unified preview, with a friendly empty-state when the
// store has no rules yet.
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getMemoryRules } from "./api";
import { MemorySingleDocLane } from "./MemorySingleDocLane";

export function MemoryRulesLane({ store }: { store: string }) {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["memory-rules", store],
    queryFn: () => getMemoryRules(store),
    enabled: Boolean(store),
  });

  return (
    <MemorySingleDocLane
      title={t("memory.lanes.rules")}
      text={q.data?.text}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("memory.rules.empty")}
    />
  );
}
