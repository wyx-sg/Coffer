// frontend/src/components/agents/AgentConversationsBulkActions.tsx
// Bulk "distill to memory" bar for the conversations table. Fans out one
// distill call per selected session with allSettled (via useBulkMutate) so one
// failure never aborts the rest; a single summary toast reports the outcome and
// the selection clears via onDone(). Distillation writes facts to the projected
// memory store, so the memory-stores list is refreshed alongside the transcript
// list. Per-session insights are not shown for a bulk run — use the per-row
// distill for that.
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { distillTranscript, type TranscriptSessionSummary } from "@/lib/api/agentChat";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

export function AgentConversationsBulkActions({
  name,
  rows,
  onDone,
}: {
  name: string;
  rows: TranscriptSessionSummary[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({
    invalidate: [["agents", name, "conversations"], ["memory-stores"]],
  });

  const runAll = async () => {
    await bulk.run(rows, (s) => distillTranscript(name, { session_id: s.session_id }));
    onDone();
  };

  return (
    <Button size="sm" variant="outline" disabled={bulk.isPending} onClick={() => void runAll()}>
      <Sparkles className="mr-1.5 size-3.5" />
      {t("agents.conversationsTab.distill")}
    </Button>
  );
}
