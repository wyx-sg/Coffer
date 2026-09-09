// frontend/src/kinds/knowledge/KnowledgeRulesLane.tsx
//
// Rules lane of the knowledge detail page: a single curated doc, shown
// through the shared file-tree lane as one file row (so every tab shares the
// "tree → preview" layout). Empty scope → no items → the lane's friendly
// empty-state. Deleting clears the rules file; the backend appends a line to
// the consolidation log, so both query keys are invalidated.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { deleteKnowledgeRules, getKnowledgeRules } from "./api";
import { KnowledgeListLane, type LaneItem } from "./KnowledgeListLane";

export function KnowledgeRulesLane({ scope }: { scope: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["knowledge-rules", scope],
    queryFn: () => getKnowledgeRules(scope),
    enabled: Boolean(scope),
  });

  const del = useMutation({
    mutationFn: () => deleteKnowledgeRules(scope),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-rules", scope] });
      void qc.invalidateQueries({ queryKey: ["knowledge-consolidation-log", scope] });
    },
  });

  // One curated doc → one row; absent (no text) → no items → empty-state.
  const items: LaneItem[] = q.data?.text
    ? [{ id: "rules", title: t("knowledge.lanes.rules"), text: q.data.text }]
    : [];

  return (
    <KnowledgeListLane
      intro={t("knowledge.lanes.intro.rules")}
      listLabel={t("knowledge.lanes.rules")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("knowledge.rules.empty")}
      selectLabel={t("knowledge.rules.select")}
      onDelete={() => del.mutate()}
      deletePending={del.isPending}
    />
  );
}
