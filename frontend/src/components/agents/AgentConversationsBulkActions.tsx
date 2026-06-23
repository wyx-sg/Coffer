// frontend/src/components/agents/AgentConversationsBulkActions.tsx
// Bulk "distill to memory" bar for the conversations table. Enqueues async
// distillation via the distill-batch endpoint (returns immediately; the table's
// status column then updates live). When the user escalated to "select all"
// (allMatching) the whole matching set is distilled server-side using the active
// search; otherwise the explicitly-selected session ids are sent. Already-
// distilled sessions are skipped server-side.
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { type TranscriptSessionSummary } from "@/lib/api/agentChat";
import { useDistillBatch } from "@/lib/hooks/useAgentChatHistory";

export function AgentConversationsBulkActions({
  name,
  rows,
  onDone,
  search,
  allMatching,
}: {
  name: string;
  rows: TranscriptSessionSummary[];
  onDone: () => void;
  /** Active search query — sent with all=true so select-all respects the filter. */
  search: string;
  /** True when the user escalated to "select all matching" across pages. */
  allMatching: boolean;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const distill = useDistillBatch(name);

  const runAll = async () => {
    // One session_id can span several transcript files (subagent sidechains), so
    // de-dupe before sending the explicit set.
    const body = allMatching
      ? { all: true, q: search.trim() || undefined }
      : { session_ids: [...new Set(rows.map((r) => r.session_id))] };
    try {
      const res = await distill.mutateAsync(body);
      toast.success(
        t("agents.conversationsTab.distillQueued", { count: res.queued, skipped: res.skipped }),
      );
      onDone();
    } catch {
      /* error already surfaced via the mutation's onError toast */
    }
  };

  return (
    <Button size="sm" variant="outline" disabled={distill.isPending} onClick={() => void runAll()}>
      <Sparkles className="mr-1.5 size-3.5" />
      {t("agents.conversationsTab.distill")}
    </Button>
  );
}
