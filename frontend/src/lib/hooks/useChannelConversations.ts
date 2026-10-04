// src/lib/hooks/useChannelConversations.ts — the latest conversations one channel started.
//
// A channel's Overview shows a handful of the conversations that came in
// through it, newest activity first. The server narrows the list to the
// channel, so this reads the first few rows; the full list is the Conversations
// page filtered by the channel.
import { useQuery } from "@tanstack/react-query";

import { chatApi, type Conversation } from "@/lib/api/chat";
import { channelRecentConversationsKey } from "@/lib/api/queryKeys";

const RECENT = 5;

export function useChannelConversations(channelUid: string) {
  return useQuery<Conversation[]>({
    queryKey: channelRecentConversationsKey(channelUid),
    queryFn: async ({ signal }) => {
      const out = await chatApi.listConversations({ limit: RECENT, source: [channelUid] }, signal);
      return out.conversations;
    },
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    enabled: !!channelUid,
  });
}
