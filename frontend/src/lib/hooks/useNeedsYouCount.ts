// src/lib/hooks/useNeedsYouCount.ts — how many conversations wait on an answer
// (GET /api/v1/chat/conversations/needs-you-count), for the sidebar's
// Conversations badge. The open conversation's `question_*` events and every
// list refresh invalidate it; the timer covers questions raised in
// conversations this page holds no stream for.
import { useQuery } from "@tanstack/react-query";

import { chatApi } from "@/lib/api/chat";
import { needsYouCountKey } from "@/lib/api/queryKeys";

const POLL_MS = 20_000;

export function useNeedsYouCount() {
  return useQuery({
    queryKey: needsYouCountKey,
    queryFn: chatApi.needsYouCount,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
}
