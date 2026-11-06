// frontend/src/lib/hooks/useChannelAskAgain.ts — the refused-secret banner's
// Ask again on a channel.
import { channelStatusKey } from "@/lib/api/queryKeys";
import { useAskAgainFor } from "./useAskAgain";

/** Ask again for this channel's refused secret; the channel starts on its next attempt once approved. */
export function useAskAgainForChannel(uid: string) {
  return useAskAgainFor(uid, [channelStatusKey(uid)]);
}
