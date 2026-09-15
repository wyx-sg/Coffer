// frontend/src/lib/hooks/useChannels.ts — TanStack Query bindings for channels.
//
// Channel resources ride the generic /resources API (kind=channel), so
// useChannels delegates to useResources and shares its ["resources", …] cache
// — the kind-agnostic useEnableResource / useDisableResource / useDeleteResource
// mutations (useResourceMutations.ts) invalidate it for free. The
// channel-specific operations (status, pairing) live under a "channels" key.
// Channels DO declare scope (ADR per-agent-resource-scope): which agents answer
// on a transport is per-agent, so the list row and the detail header both mount
// the shared reach control. The scope binding itself is generic
// (useScope.ts) — there is nothing channel-specific about it, so none here.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { getChannelStatus, issuePairingCode, notifyChannel } from "@/lib/api/channels";
import { applyChannelEdit } from "@/components/channel/editChannel";
import { createChannel } from "@/components/channel/registerChannel";
import type { ChannelPlan } from "@/components/channel/schema";
import { useResources } from "@/lib/hooks/useResources";
import { useToast } from "@/components/ui/toast";
import { channelStatusKey, resourcesKey } from "@/lib/api/queryKeys";

export const CHANNEL_KIND = "channel";

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
      void qc.invalidateQueries({ queryKey: resourcesKey });
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

/**
 * Register a new channel: secrets first, then the resource, rolling the
 * secrets back when registration fails (registerChannel.ts). The resources
 * cache is invalidated so the list shows the new row; what happens next
 * (toast, navigate, close the dialog) is the caller's, via `mutate(plan,
 * { onSuccess })`.
 */
export function useCreateChannel() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (plan: ChannelPlan) => createChannel(plan),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
