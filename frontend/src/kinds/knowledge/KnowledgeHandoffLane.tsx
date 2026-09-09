// frontend/src/kinds/knowledge/KnowledgeHandoffLane.tsx
//
// Handoff lane of the knowledge detail page: the per-branch scene notes
// (`handoff/<branch-slug>.md`) in a left list (branch + last-updated) → select
// → the scene rendered read-only through the unified preview, with an
// open/reveal/delete toolbar. Deleting a scene also touches the consolidation
// log (the backend appends a line), so we invalidate both query keys.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { formatDateTime } from "@/lib/utils";
import { deleteHandoffBranch, getKnowledgeHandoff } from "./api";
import { KnowledgeListLane, type LaneItem } from "./KnowledgeListLane";

export function KnowledgeHandoffLane({ scope }: { scope: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["knowledge-handoff", scope],
    queryFn: () => getKnowledgeHandoff(scope),
    enabled: Boolean(scope),
  });

  const del = useMutation({
    mutationFn: (branch: string) => deleteHandoffBranch(scope, branch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-handoff", scope] });
      void qc.invalidateQueries({ queryKey: ["knowledge-consolidation-log", scope] });
    },
  });

  const items: LaneItem[] = (q.data?.scenes ?? []).map((s) => ({
    id: s.branch,
    title: s.branch,
    subtitle: t("knowledge.handoff.updatedAt", { time: formatDateTime(s.updated_at) }),
    text: s.text,
    path: s.path,
  }));

  return (
    <KnowledgeListLane
      intro={t("knowledge.lanes.intro.handoff")}
      listLabel={t("knowledge.lanes.handoff")}
      items={items}
      isLoading={q.isPending}
      error={q.error}
      emptyLabel={t("knowledge.handoff.empty")}
      selectLabel={t("knowledge.handoff.select")}
      onDelete={(item) => del.mutate(item.id)}
      deletePending={del.isPending}
    />
  );
}
