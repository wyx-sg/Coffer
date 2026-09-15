// frontend/src/lib/hooks/useMessageThread.ts
// The persisted message list of the open conversation, shaped for the thread:
// while a live bubble is shown, fetched streaming placeholder rows are dropped so
// a mid-turn refetch (e.g. window refocus) can't duplicate the in-progress reply,
// and after a failed turn an empty placeholder is dropped so nothing keeps
// "thinking" beside the error banner (lib/chat/threadView decides).
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { chatApi, type Message } from "@/lib/api/chat";
import { messagesKey } from "@/lib/api/queryKeys";
import { visibleThreadMessages } from "@/lib/chat/threadView";
import type { LiveMessage } from "@/lib/hooks/chatTurnEvents";

export function useMessageThread(
  conversationId: string,
  liveMessage: LiveMessage | null,
  turnError: unknown = null,
) {
  const { data, isPending, error } = useQuery({
    queryKey: messagesKey(conversationId),
    queryFn: async () => (await chatApi.listMessages(conversationId)).messages,
    // No polling: the persistent /events subscription drives the live turn and
    // invalidates this query when the turn ends.
  });

  const messages = useMemo<Message[]>(
    () => visibleThreadMessages(data ?? [], liveMessage, turnError),
    [data, liveMessage, turnError],
  );

  return { messages, isPending, error };
}
