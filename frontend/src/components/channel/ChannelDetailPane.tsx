// frontend/src/components/channel/ChannelDetailPane.tsx
// The open channel in the Channels page's right pane: the header (state,
// Send test, ⋯ menu), the banner (or grey box) that says what is wrong and
// holds its fix, and two tabs
// — Overview and Settings. The page owns the address (`/channels/<uid>` and
// `/channels/<uid>/settings`); this pane runs the commands and owns their
// dialogs: send test, replace secret, re-pair, delete.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ChannelPerson } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";
import type { ChannelTab } from "@/lib/channels/tabs";
import {
  CHANNEL_KIND,
  useChannelAutoSave,
  useChannelView,
  useReconnectChannel,
} from "@/lib/hooks/useChannels";
import { useRemoveChannelPerson } from "@/lib/hooks/useChannelPairing";
import { useDeleteResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { ChannelDetailHeader, type ChannelCommand } from "./ChannelDetailHeader";
import { channelHeading } from "./channelLabels";
import { ChannelOverviewTab } from "./ChannelOverviewTab";
import { ChannelPeopleDialogs } from "./ChannelPeopleDialogs";
import { ChannelPairDialog } from "./ChannelPairDialog";
import { ChannelReplaceSecretDialog } from "./ChannelReplaceSecretDialog";
import { ChannelSendTestDialog } from "./ChannelSendTestDialog";
import { ChannelSettingsTab } from "./ChannelSettingsTab";
import { channelPlatform } from "@/lib/channels/channelState";
import { ChannelStatusBanner } from "./ChannelStatusBanner";
import { platformLabel } from "./PlatformMark";

type Dialog = "test" | "secret" | "delete" | "remove" | null;

interface Props {
  channel: ResourceOut;
  tab: ChannelTab;
  onTabChange: (tab: string) => void;
  /** Called once the delete has landed, to leave the address of a channel that is gone. */
  onDeleted: () => void | Promise<void>;
}

export function ChannelDetailPane({ channel, tab, onTabChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { status, view } = useChannelView(channel);
  const removePerson = useRemoveChannelPerson(channel.uid);
  const reconnect = useReconnectChannel(channel.uid);
  const enable = useEnableResource();
  const del = useDeleteResource();
  const { save } = useChannelAutoSave(channel);
  const [dialog, setDialog] = useState<Dialog>(null);
  // The pairing dialog (Add owner): open or not.
  const [pairOpen, setPairOpen] = useState(false);
  // The person the Remove… dialog is about.
  const [target, setTarget] = useState<ChannelPerson | null>(null);

  const platform = channelPlatform(channel.config);
  const name = channelHeading(channel);
  const people = status.data?.people ?? [];
  // The name the dialogs and the test message use: the first paired owner.
  const firstOwner = people[0]?.display_name ?? "";
  const openPair = () => setPairOpen(true);
  const setDialogOpen = (which: Dialog) => (open: boolean) => setDialog(open ? which : null);

  const onCommand = (command: ChannelCommand) => {
    switch (command) {
      case "sendTest":
      case "replaceSecret":
        setDialog(command === "sendTest" ? "test" : "secret");
        return;
      case "reconnect":
      case "takeBack":
      case "retryStart":
        reconnect.mutate();
        return;
      case "openSecrets":
        void navigate("/secrets");
        return;
      case "refresh":
        void status.refetch();
        return;
      case "turnOn":
        enable.mutate({ kind: CHANNEL_KIND, uid: channel.uid });
        return;
    }
  };

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <ChannelDetailHeader
        channel={channel}
        view={view}
        busy={reconnect.isPending || enable.isPending}
        onCommand={onCommand}
      />
      <ChannelStatusBanner
        channel={channel}
        view={view}
        status={status.data}
        busy={reconnect.isPending || enable.isPending}
        onCommand={onCommand}
        onPair={openPair}
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
            onAdd={openPair}
            onRemove={(person) => {
              setTarget(person);
              setDialog("remove");
            }}
            onDefaultAgentChange={(agent) => void save({ default_agent: agent })}
            onDefaultModelChange={(model) => void save({ default_model: model })}
          />
        </TabsContent>
        <TabsContent value="settings">
          {status.data?.settings ? (
            <ChannelSettingsTab
              key={channel.uid}
              channel={channel}
              settings={status.data.settings}
              workspaceDirectory={status.data.workspace_directory}
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
        owner={firstOwner}
        open={dialog === "test"}
        onOpenChange={setDialogOpen("test")}
      />
      <ChannelReplaceSecretDialog
        channel={channel}
        open={dialog === "secret"}
        onOpenChange={setDialogOpen("secret")}
      />
      <ChannelPairDialog
        uid={channel.uid}
        platform={platform}
        open={pairOpen}
        onOpenChange={setPairOpen}
      />
      <ChannelPeopleDialogs
        dialog={dialog === "remove" ? dialog : null}
        onOpenChange={(open) => setDialog(open ? dialog : null)}
        channelName={name}
        target={target}
        isLastOwner={people.length <= 1}
        removePending={removePerson.isPending}
        onRemove={(senderId) => removePerson.mutateAsync(senderId)}
      />
      <ConfirmDialog
        open={dialog === "delete"}
        onOpenChange={setDialogOpen("delete")}
        title={t("channels.delete.title", { name })}
        description={t(
          people.length > 0 ? "channels.delete.body" : "channels.delete.bodyUnpaired",
          {
            platform: platformLabel(platform),
          },
        )}
        confirmLabel={t("channels.actions.delete")}
        pending={del.isPending}
        onConfirm={() => del.mutateAsync({ kind: CHANNEL_KIND, uid: channel.uid }).then(onDeleted)}
      />
    </div>
  );
}
