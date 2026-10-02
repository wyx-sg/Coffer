// frontend/src/components/channel/ChannelDetailPane.tsx
// The open channel in the Channels page's right pane: the header (state,
// primary action, ⋯ menu), the banner that explains any failure, and two tabs
// — Overview and Settings. The page owns the address (`/channels/<uid>` and
// `/channels/<uid>/settings`); this pane runs the commands and owns their
// dialogs: send test, replace secret, run it here, re-pair, delete.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";
import type { ChannelTab } from "@/lib/channels/tabs";
import {
  CHANNEL_KIND,
  useChannelAutoSave,
  useChannelView,
  useIssuePairingCode,
  useRebindChannel,
  useReconnectChannel,
} from "@/lib/hooks/useChannels";
import { useDeleteResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { displayName } from "@/lib/resourceTitle";
import { ChannelDetailHeader, type ChannelCommand } from "./ChannelDetailHeader";
import { channelHeading, useMachineName } from "./channelLabels";
import { ChannelOverviewTab } from "./ChannelOverviewTab";
import { ChannelPairingCode } from "./ChannelPairingCode";
import { ChannelReplaceSecretDialog } from "./ChannelReplaceSecretDialog";
import { ChannelSendTestDialog } from "./ChannelSendTestDialog";
import { ChannelSettingsTab } from "./ChannelSettingsTab";
import { channelPlatform } from "@/lib/channels/channelState";
import { ChannelStatusBanner } from "./ChannelStatusBanner";
import { platformLabel } from "./PlatformMark";

type Dialog = "test" | "secret" | "delete" | "runHere" | "repair" | null;

interface Props {
  channel: ResourceOut;
  tab: ChannelTab;
  onTabChange: (tab: string) => void;
  /** Called once the delete has landed, to leave the address of a channel that is gone. */
  onDeleted: () => void | Promise<void>;
}

export function ChannelDetailPane({ channel, tab, onTabChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const { status, view, selfId } = useChannelView(channel);
  const machineName = useMachineName();
  const pairing = useIssuePairingCode(channel.uid);
  const reconnect = useReconnectChannel(channel.uid);
  const rebind = useRebindChannel(channel.uid, displayName(channel));
  const enable = useEnableResource();
  const del = useDeleteResource();
  const { save } = useChannelAutoSave(channel);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [issuedAt, setIssuedAt] = useState(0);

  const platform = channelPlatform(channel.config);
  const name = channelHeading(channel);
  const peer = status.data?.peer ?? null;
  // A code is spent once somebody paired after it was issued.
  const consumed = peer !== null && new Date(peer.paired_at).getTime() >= issuedAt - 5_000;
  const code = pairing.data && !consumed ? pairing.data : undefined;
  const generate = () => {
    setIssuedAt(Date.now());
    return pairing.mutateAsync();
  };
  const pairingPanel = (
    <ChannelPairingCode
      platform={platform}
      code={code}
      isPending={pairing.isPending}
      onGenerate={() => void generate().catch(() => undefined)}
    />
  );
  const setDialogOpen = (which: Dialog) => (open: boolean) => setDialog(open ? which : null);
  const runHere = () =>
    rebind.mutateAsync({
      config: channel.config,
      runsOn: selfId ?? "",
      machine: t("channels.machine.thisMachine"),
    });

  const onCommand = (command: ChannelCommand) => {
    switch (command) {
      case "sendTest":
      case "replaceSecret":
      case "delete":
        setDialog(command === "sendTest" ? "test" : command === "delete" ? "delete" : "secret");
        return;
      case "reconnect":
      case "takeBack":
      case "retryStart":
        reconnect.mutate();
        return;
      case "refresh":
        void status.refetch();
        return;
      case "runHere":
        if (selfId) void runHere().catch(() => undefined);
        return;
      case "runHereConfirm":
        setDialog("runHere");
        return;
      case "turnOn":
        enable.mutate({ kind: CHANNEL_KIND, uid: channel.uid });
        return;
      case "changeMachine":
        onTabChange("settings");
        return;
    }
  };

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <ChannelDetailHeader
        channel={channel}
        view={view}
        hasPeer={peer !== null}
        busy={reconnect.isPending || rebind.isPending || enable.isPending}
        onCommand={onCommand}
      />
      <ChannelStatusBanner
        channel={channel}
        view={view}
        status={status.data}
        statusError={status.error ? translateApiError(t, status.error) : null}
        pairing={pairingPanel}
      />

      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          <TabsTrigger value="overview">{t("channels.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="settings">{t("channels.tabs.settings")}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <ChannelOverviewTab
            channel={channel}
            status={status.data}
            pairing={pairingPanel}
            showPairing={view.state !== "notPaired" && (peer === null || code !== undefined)}
            onRepair={() => setDialog("repair")}
            onDefaultAgentChange={(agent) => void save({ default_agent: agent })}
          />
        </TabsContent>
        <TabsContent value="settings">
          {status.data?.settings ? (
            <ChannelSettingsTab
              key={channel.uid}
              channel={channel}
              settings={status.data.settings}
              onReplaceSecret={() => setDialog("secret")}
              onDelete={() => setDialog("delete")}
            />
          ) : status.data ? (
            // Stored settings that no longer validate: say so instead of
            // guessing values for them.
            <p className="text-sm text-text-muted">{t("channels.settings.unavailable")}</p>
          ) : null}
        </TabsContent>
      </Tabs>

      <ChannelSendTestDialog
        uid={channel.uid}
        owner={peer?.display_name ?? ""}
        open={dialog === "test"}
        onOpenChange={setDialogOpen("test")}
      />
      <ChannelReplaceSecretDialog
        channel={channel}
        open={dialog === "secret"}
        onOpenChange={setDialogOpen("secret")}
      />
      <ConfirmDialog
        open={dialog === "runHere"}
        onOpenChange={setDialogOpen("runHere")}
        variant="default"
        title={t("channels.runHere.title", { name })}
        description={t("channels.runHere.body", { machine: machineName(view.runsOn) })}
        confirmLabel={t("channels.actions.runHere")}
        pending={rebind.isPending}
        onConfirm={runHere}
      />
      <ConfirmDialog
        open={dialog === "repair"}
        onOpenChange={setDialogOpen("repair")}
        variant="default"
        title={t("channels.repair.title", { name })}
        description={t("channels.repair.body", { owner: peer?.display_name ?? "" })}
        confirmLabel={t("channels.repair.confirm")}
        pending={pairing.isPending}
        onConfirm={generate}
      />
      <ConfirmDialog
        open={dialog === "delete"}
        onOpenChange={setDialogOpen("delete")}
        title={t("channels.delete.title", { name })}
        description={t(peer ? "channels.delete.body" : "channels.delete.bodyUnpaired", {
          owner: peer?.display_name ?? "",
          platform: platformLabel(platform),
        })}
        confirmLabel={t("channels.actions.delete")}
        pending={del.isPending}
        onConfirm={() => del.mutateAsync({ kind: CHANNEL_KIND, uid: channel.uid }).then(onDeleted)}
      />
    </div>
  );
}
