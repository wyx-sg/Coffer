// frontend/src/lib/hooks/useChannels.ts — TanStack Query bindings for channels.
//
// Channel resources ride the generic /resources API (kind=channel), so
// useChannels delegates to useResources and shares its ["resources", …] cache;
// enable / disable / delete / reach are the generic mutations. What is
// channel-specific lives here: live status and the state it puts a channel in,
// pairing, notify, reconnect, the settings auto-save, and the machine binding
// (`runs_on`, written through the same config PATCH an edit uses).
import { useCallback, useEffect, useRef } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { withInlineApproval } from "@/lib/inlineApproval";
import { secretsApi } from "@/lib/api/secret";
import {
  getChannelPersonAvatar,
  getChannelStatus,
  notifyChannel,
  restartChannel,
} from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import { describeChannel, type ChannelView } from "@/lib/channels/channelState";
import {
  applyChannelEdit,
  planChannelEdit,
  type ChannelEditValues,
} from "@/lib/channels/editChannel";
import { createChannel } from "@/lib/channels/registerChannel";
import type { ChannelEditPlan, ChannelPlan } from "@/lib/channels/schema";
import { useMachines, useThisMachineId } from "@/lib/hooks/useMachines";
import { useResources } from "@/lib/hooks/useResources";
import { useToast } from "@/components/ui/toast";
import {
  channelAvatarKey,
  channelStatusKey,
  pendingApprovalsKey,
  resourcesKey,
} from "@/lib/api/queryKeys";

export const CHANNEL_KIND = "channel";

/** List channel resources (name, config, enabled) via the generic resources API. */
export function useChannels() {
  return useResources(CHANNEL_KIND);
}

/**
 * Live status of one channel (adapter running, paired peer, inbound state).
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

/**
 * A paired person's picture (`data:` URL), or `null` while there is none — the
 * people list shows initials then. The daemon keeps the picture a day, so the
 * page asks once an hour rather than on every status poll.
 */
export function useChannelPersonAvatar(uid: string, senderId: string) {
  return useQuery({
    queryKey: channelAvatarKey(uid, senderId),
    queryFn: () => getChannelPersonAvatar(uid, senderId),
    enabled: uid.length > 0 && senderId.length > 0,
    staleTime: 60 * 60_000,
    retry: false,
  });
}

/**
 * Every listed channel's state, for the list's groups and rows. One status
 * query per channel on the same key the open channel polls, so the open row
 * and the header always read one answer; non-polling here (the change feed and
 * the open channel's poll keep them fresh).
 */
export function useChannelViews(channels: readonly ResourceOut[]): Map<string, ChannelView> {
  const statuses = useQueries({
    queries: channels.map((c) => ({
      queryKey: channelStatusKey(c.uid),
      queryFn: () => getChannelStatus(c.uid),
      staleTime: 15_000,
    })),
  });
  const { data: machineList } = useMachines();
  const { machineId: selfId } = useThisMachineId();
  const known = (machineList?.machines ?? []).map((m) => m.machine_id);
  const views = new Map<string, ChannelView>();
  channels.forEach((c, i) => {
    const q = statuses[i];
    views.set(
      c.uid,
      describeChannel({
        enabled: c.enabled,
        config: c.config,
        status: q?.data,
        statusFailed: q?.isError ?? false,
        selfId,
        knownMachines: known,
      }),
    );
  });
  return views;
}

/** The open channel's live status (polled) and the state it puts it in. */
export function useChannelView(channel: ResourceOut) {
  const status = useChannelStatus(channel.uid, { poll: true });
  const { data: machineList } = useMachines();
  const { machineId: selfId } = useThisMachineId();
  const view = describeChannel({
    enabled: channel.enabled,
    config: channel.config,
    status: status.data,
    statusFailed: status.isError,
    selfId,
    knownMachines: (machineList?.machines ?? []).map((m) => m.machine_id),
  });
  return { status, view, selfId };
}

/**
 * Restart a channel's adapter (`POST /channels/{uid}/restart`): the daemon
 * stops it and starts a fresh one that reads its secret again and dials the
 * platform anew — which also takes a SeaTalk connection back from whatever
 * process was handed it.
 */
export function useReconnectChannel(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => restartChannel(uid),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * The refused-secret banner's Ask again: puts each refused request for this
 * channel's secret back in front of the owner. In the desktop app the request
 * is approved on the spot with Touch ID (the mutation opts in to inline
 * approval); in a browser it waits on the approvals list. The channel starts
 * on its next attempt once it is approved.
 */
export function useAskAgainForChannel(uid: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async () => {
      const { approvals } = await secretsApi.rejectedApprovalsFor(uid);
      return Promise.all(approvals.map((a) => secretsApi.askAgain(a.id)));
    },
    meta: { secretDestination: () => uid },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Save a channel's settings as they change (the Settings tab has no Save
 * button). Each call PATCHes the whole config, so calls are queued and each
 * plans from the config the previous one wrote — two fields saved a moment
 * apart must not each PATCH back the config from before the other. A failure
 * is toasted; the field keeps what was typed. Resolves to whether it landed.
 */
export function useChannelAutoSave(channel: ResourceOut) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  const latest = useRef(channel.config);
  const pending = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());

  // Adopt the server's config whenever it changes and nothing is in flight.
  useEffect(() => {
    if (pending.current === 0) latest.current = channel.config;
  }, [channel.config]);

  const save = useCallback(
    (values: Partial<ChannelEditValues>): Promise<boolean> => {
      pending.current += 1;
      const run = queue.current.then(async (): Promise<boolean> => {
        const config = latest.current;
        const agent = typeof config.default_agent === "string" ? config.default_agent : "";
        const plan = planChannelEdit({
          uid: channel.uid,
          name: channel.name,
          config,
          values: { default_agent: agent, ...values },
        });
        try {
          await withInlineApproval(
            () => applyChannelEdit(plan),
            (written) => written.uid,
          );
          latest.current = plan.config;
          void qc.invalidateQueries({ queryKey: resourcesKey });
          void qc.invalidateQueries({ queryKey: channelStatusKey(channel.uid) });
          void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
          return true;
        } catch (error) {
          toast.error(translateApiError(t, error));
          return false;
        } finally {
          pending.current -= 1;
        }
      });
      queue.current = run.then(() => undefined);
      return run;
    },
    [channel.uid, channel.name, qc, t, toast],
  );

  return { save };
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
    meta: { secretDestination: (data: unknown) => (data as { uid: string }).uid },
    // The apply hands back the channel it wrote: the uid to refresh the status
    // under, and the name to put in the toast. Two answers, two fields — the
    // one string that used to serve both is exactly what this change split.
    onSuccess: ({ uid, name }) => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      void qc.invalidateQueries({ queryKey: channelStatusKey(uid) });
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
      toast.success(t("channels.edit.saved", { name }));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** @ui-only What a rebind needs: the channel's CURRENT config (so the PATCH
 *  keeps every ref and platform field) and the machine it should run on. */
export interface ChannelRebind {
  config: Record<string, unknown>;
  runsOn: string;
  /** Display name of the target machine — the toast's, not the wire's. */
  machine: string;
}

/**
 * Move a channel's adapter to another machine (spec channels "Bind each channel
 * to the one machine that runs it"). The binding is an ordinary config field,
 * so this is an ordinary config PATCH — there is no command that reaches
 * across to the other machine and none is needed: each daemon reconciles
 * against the document it holds.
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

/** Push a test message to the channel's first paired owner (notify capability). */
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
    meta: { secretDestination: (data: unknown) => (data as ResourceOut).uid },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
