// frontend/src/lib/hooks/useMessageThread.ts
// The persisted message list of the open conversation, shaped for the thread:
// while a live bubble is shown, fetched streaming placeholder rows are dropped so
// a mid-turn refetch (e.g. window refocus) can't duplicate the in-progress reply.
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { chatApi, type Message } from "@/lib/api/chat";
import { messagesKey } from "@/lib/api/queryKeys";

export function useMessageThread(conversationId: string, hasLiveMessage: boolean) {
  const { data, isPending, error } = useQuery({
    queryKey: messagesKey(conversationId),
    queryFn: async () => (await chatApi.listMessages(conversationId)).messages,
    // No polling: the persistent /events subscription drives the live turn and
    // invalidates this query when the turn ends.
  });

  const messages = useMemo<Message[]>(() => {
    const rows = data ?? [];
    return hasLiveMessage ? rows.filter((m) => m.status !== "streaming") : rows;
  }, [data, hasLiveMessage]);

  return { messages, isPending, error };
}
