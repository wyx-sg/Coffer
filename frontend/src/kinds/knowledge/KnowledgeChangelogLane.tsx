// frontend/src/kinds/knowledge/KnowledgeChangelogLane.tsx
//
// Changelog lane of the knowledge detail page: the consolidation log
// (`consolidation-log.md`), now shown through the shared file-tree lane as one
// file row (so every tab shares the "tree → preview" layout). Empty scope → no
// items → the lane's friendly empty-state. Deleting the log does NOT self-append
// a changelog line, so only its own query key is invalidated.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { deleteConsolidationLog, getConsolidationLog } from "./api";
import { KnowledgeListLane, type LaneItem } from "./KnowledgeListLane";

export function KnowledgeChangelogLane({ scope }: { scope: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["knowledge-consolidation-log", scope],
    queryFn: () => getConsolidationLog(scope),
    enabled: Boolean(scope),
  });

  const del = useMutation({
    mutationFn: () => deleteConsolidationLog(scope),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-consolidation-log", scope] });
    },
  });

  // The log is one doc → one row (with its on-disk path); absent → empty-state.
  const items: LaneItem[] = q.data?.text
    ? [
        {
          id: "changelog",
          title: t("knowledge.lanes.changelog"),
          text: q.data.text,
          path: q.data.path,
        },
      ]
    : [];

  return (
    <KnowledgeListLane
      intro={t("knowledge.lanes.intro.changelog")}
      listLabel={t("knowledge.lanes.changelog")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("knowledge.changelog.empty")}
      selectLabel={t("knowledge.changelog.select")}
      onDelete={() => del.mutate()}
      deletePending={del.isPending}
    />
  );
}
