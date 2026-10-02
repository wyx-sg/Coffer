// src/lib/hooks/useChannelConversations.ts — the latest conversations one channel started.
//
// A channel's Overview shows a handful of the conversations that came in
// through it, newest activity first, each a link into Conversations. The list
// endpoint is not filterable by channel, so this reads the newest page and
// keeps this channel's rows — enough for "recent"; the full list is the
// Conversations page filtered by the channel.
import { useQuery } from "@tanstack/react-query";

import { chatApi, type Conversation } from "@/lib/api/chat";
import { channelRecentConversationsKey } from "@/lib/api/queryKeys";

const RECENT = 5;
const WINDOW = 50;

export function useChannelConversations(channelUid: string) {
  return useQuery<Conversation[]>({
    queryKey: channelRecentConversationsKey(channelUid),
    queryFn: async ({ signal }) => {
      const out = await chatApi.listConversations(
        { archived: false, q: "", limit: WINDOW },
        signal,
      );
      return out.conversations
        .filter((c) => c.channel_binding?.channel_uid === channelUid)
        .slice(0, RECENT);
    },
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    enabled: !!channelUid,
  });
}
