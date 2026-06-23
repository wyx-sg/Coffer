// frontend/src/components/agents/AgentConversationsDistillButton.tsx
// Per-row "Distill to memory" action for the conversations table. Enqueues a
// single-session async batch distill (returns 202 at once) so the work runs off
// the request path; the row's status column then polls queued → running → done.
// Mirrors the Memory tab's per-row native-memory import: a summary toast confirms
// the enqueue and the distilled insights are written to memory, never rendered
// inline in the table.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { TranscriptSessionSummary } from "@/lib/api/agentChat";
import { useDistillBatch } from "@/lib/hooks/useAgentChatHistory";

export function DistillButton({
  session,
  name,
}: {
  session: TranscriptSessionSummary;
  name: string;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const distill = useDistillBatch(name);
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={distill.isPending}
      aria-label={t("agents.conversationsTab.distillAria", { session: session.session_id })}
      onClick={() =>
        distill.mutate(
          { session_ids: [session.session_id] },
          {
            onSuccess: (r) =>
              toast.success(
                t("agents.conversationsTab.distillQueued", {
                  count: r.queued,
                  skipped: r.skipped,
                }),
              ),
            onError: (e) => toast.error(translateApiError(t, e)),
          },
        )
      }
    >
      {distill.isPending
        ? t("agents.conversationsTab.distilling")
        : t("agents.conversationsTab.distill")}
    </Button>
  );
}
