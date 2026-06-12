// frontend/src/lib/hooks/useChannels.ts — TanStack Query bindings for channels.
//
// Channel resources ride the generic /resources API (kind=channel), so
// useChannels delegates to useResources and shares its ["resources", …] cache
// — the kind-agnostic useEnableResource / useDisableResource / useDeleteResource
// mutations (useResourceMutations.ts) invalidate it for free. The
// channel-specific operations (status, pairing) live under a "channels" key.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getChannelStatus, issuePairingCode } from "@/lib/api/channels";
import { useResources } from "@/lib/hooks/useResources";

export const CHANNEL_KIND = "channel";

export function channelStatusKey(name: string) {
  return ["channels", name, "status"] as const;
}

/** List channel resources (name, config, enabled) via the generic resources API. */
export function useChannels() {
  return useResources(CHANNEL_KIND);
}

/**
 * Live status of one channel (adapter running, paired peer, callback info).
 * Pass `poll: true` on surfaces that stay open (the detail page) so pairing
 * confirmations and adapter restarts show up without a manual refresh.
 */
export function useChannelStatus(name: string, opts: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: channelStatusKey(name),
    queryFn: () => getChannelStatus(name),
    enabled: name.length > 0,
    refetchInterval: opts.poll ? 5_000 : false,
    refetchIntervalInBackground: false,
    // Non-polling consumers (the per-row paired cell on the list page) must
    // not re-fan-out N status requests on every navigation.
    staleTime: opts.poll ? 0 : 15_000,
  });
}

/** Issue a pairing code; refreshes the status (pending_pairing) on success. */
export function useIssuePairingCode(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => issuePairingCode(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(name) });
    },
  });
}
