// src/lib/hooks/useConversationBatch.ts
// Archive, unarchive or delete several conversations in one call (POST
// /chat/conversations/batch). The daemon answers per id, so a conversation that
// is gone or still running never blocks the rest: one summary toast says how
// many were done and how many skipped (running ones named), the lists refresh
// once, and the caller learns which ids were done. An archive toast carries Undo.
import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { chatApi, type ConversationBatchAction } from "@/lib/api/chat";
import { conversationKey, conversationsKey, messagesKey } from "@/lib/api/queryKeys";

export function useConversationBatch() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [isPending, setPending] = useState(false);

  const run = useCallback(
    async (action: ConversationBatchAction, ids: string[]): Promise<string[]> => {
      setPending(true);
      try {
        const { results } = await chatApi.batchConversations(action, ids);
        const done = results.filter((r) => r.outcome === "done").map((r) => r.id);
        const skipped = results.length - done.length;
        const running = results.filter((r) => r.reason === "running").length;
        if (action === "delete") {
          for (const id of done) {
            qc.removeQueries({ queryKey: conversationKey(id) });
            qc.removeQueries({ queryKey: messagesKey(id) });
          }
        }
        void qc.invalidateQueries({ queryKey: conversationsKey });
        if (skipped === 0) {
          toast.success(t(`conversations.bulk.done.${action}`, { count: done.length }), {
            undo: action === "archive" ? () => void run("unarchive", done) : undefined,
          });
        } else {
          toast.error(
            done.length === 0
              ? t("conversations.bulk.noneDone", { count: skipped })
              : t("conversations.bulk.partial", { ok: done.length, skipped }),
            running > 0
              ? { details: t("conversations.bulk.runningSkipped", { count: running }) }
              : {},
          );
        }
        return done;
      } catch (e) {
        toast.error(translateApiError(t, e));
        return [];
      } finally {
        setPending(false);
      }
    },
    [t, toast, qc],
  );

  return { run, isPending };
}
