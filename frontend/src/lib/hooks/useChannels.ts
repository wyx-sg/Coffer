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
// The machine BINDING is the other axis and is channel-specific: it lives in
// the channel's own config (`runs_on`), travels with the document, and is
// written through the same config PATCH an edit uses — see useRebindChannel.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { getChannelStatus, issuePairingCode, notifyChannel } from "@/lib/api/channels";
import { applyChannelEdit } from "@/components/channel/editChannel";
import { createChannel } from "@/components/channel/registerChannel";
import type { ChannelEditPlan, ChannelPlan } from "@/components/channel/schema";
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
export function useChannelStatus(uid: string, opts: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: channelStatusKey(uid),
    queryFn: () => getChannelStatus(uid),
    enabled: uid.length > 0,
    refetchInterval: opts.poll ? 5_000 : false,
    refetchIntervalInBackground: false,
    // Non-polling consumers (the per-row paired cell on the list page) must
    // not re-fan-out N status requests on every navigation.
    staleTime: opts.poll ? 0 : 15_000,
  });
}

/** Issue a pairing code; refreshes the status (pending_pairing) on success. */
export function useIssuePairingCode(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => issuePairingCode(uid),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
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
    mutationFn: (plan: ChannelEditPlan) => applyChannelEdit(plan),
    // The apply hands back the channel it wrote: the uid to refresh the status
    // under, and the name to put in the toast. Two answers, two fields — the
    // one string that used to serve both is exactly what this change split.
    onSuccess: ({ uid, name }) => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
      toast.success(t("channels.edit.saved", { name }));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** What a rebind needs: the channel's CURRENT config (so the PATCH preserves
 *  every credential ref and platform field beside the binding) and the machine
 *  it should run on. */
export interface ChannelRebind {
  config: Record<string, unknown>;
  runsOn: string;
  /** Display name of the target machine — the toast's, not the wire's. */
  machine: string;
}

/**
 * Move a channel's adapter to another machine (spec channels, "Where a channel
 * runs"). The binding is an ordinary config field, so this is an ordinary
 * config PATCH — there is no command that reaches across to the other machine
 * and none is needed: each daemon reconciles against the document it holds.
 *
 * Both caches move: the resource list carries `config.runs_on` for the table,
 * and the channel status carries the daemon's own `runs_here` plus the
 * unbound diagnostic this may have just cleared.
 */
export function useRebindChannel(uid: string, name: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ config, runsOn }: ChannelRebind) =>
      applyChannelEdit({ uid, name, config: { ...config, runs_on: runsOn }, secrets: [] }),
    onSuccess: (_written, { machine }) => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
      toast.success(t("channels.machine.rebound", { name, machine }));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Push a test message to the channel's paired peer (notify capability). */
export function useNotifyChannel(uid: string) {
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (text: string) => notifyChannel(uid, text),
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
