// frontend/src/lib/hooks/useChannels.ts — TanStack Query bindings for channels.
//
// Channel resources ride the generic /resources API (kind=channel), so
// useChannels delegates to useResources and shares its ["resources", …] cache
// — the kind-agnostic useEnableResource / useDisableResource / useDeleteResource
// mutations (useResourceMutations.ts) invalidate it for free. The
// channel-specific operations (status, pairing) live under a "channels" key.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { getChannelStatus, issuePairingCode, notifyChannel } from "@/lib/api/channels";
import { applyChannelEdit } from "@/kinds/channel/editChannel";
import type { ChannelPlan } from "@/kinds/channel/schema";
import { useResources } from "@/lib/hooks/useResources";
import { useToast } from "@/components/ui/toast";

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
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => issuePairingCode(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(name) });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Apply an edit to a channel: rotate the changed secrets into their existing
 * refs, then PATCH the mutable config (bound agent, SeaTalk app id). The
 * resources cache is invalidated so the detail view reflects the new config.
 */
export function useUpdateChannel() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (plan: ChannelPlan) => applyChannelEdit(plan),
    onSuccess: (name) => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      void qc.invalidateQueries({ queryKey: channelStatusKey(name) });
      toast.success(t("channels.edit.saved", { name }));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Push a test message to the channel's paired peer (notify capability). */
export function useNotifyChannel(name: string) {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (text: string) => notifyChannel(name, text),
    onSuccess: () => toast.success(t("channels.test.sent")),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
