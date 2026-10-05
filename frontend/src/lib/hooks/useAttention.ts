// src/lib/hooks/useAttention.ts — the cross-kind "needs you" list (GET /api/v1/attention).
//
// What needs a person now, from every source whose feature is on (spec
// resource-framework "Report what needs a person across every kind"). A page
// that shows it live mounts `useDaemonEvents`: a change in what the list
// reports arrives on the daemon's event stream as a `change` of kind
// `attention`, which invalidates this key. A reader on a page with no stream
// open passes a slow `refetchInterval`.
import { useQuery } from "@tanstack/react-query";

import { attentionApi, type AttentionItem } from "@/lib/api/attention";
import { attentionKey } from "@/lib/api/queryKeys";

export type { AttentionItem };

interface Options {
  /** Re-read on a timer, for a reader with no event stream of its own. */
  refetchInterval?: number;
  /** False leaves the list unread (e.g. a reader that only exists in the desktop shell). */
  enabled?: boolean;
}

export function useAttention({ refetchInterval, enabled = true }: Options = {}) {
  return useQuery({
    queryKey: attentionKey,
    refetchInterval,
    enabled,
    refetchIntervalInBackground: false,
    queryFn: attentionApi.read,
  });
}
