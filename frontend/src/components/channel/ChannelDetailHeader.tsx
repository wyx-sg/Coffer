// frontend/src/components/channel/ChannelDetailHeader.tsx
// The top of the open channel: its platform mark, "SeaTalk · Team bot", the
// status pill, one meta line (app id, transport, where it runs), the one
// primary action the state calls for, and the ⋯ menu with the rest — Send
// test message, Reconnect, Change machine…, Replace app secret… / bot token…,
// Delete channel….
import { useTranslation } from "react-i18next";
import { KeyRound, Play, Power, RefreshCw, Send } from "lucide-react";

import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { ResourceOut } from "@/lib/api/resources";
import { channelHeading, useChannelMeta, useChannelStateWords } from "./channelLabels";
import type { ChannelPrimaryAction, ChannelView } from "./channelState";
import { channelPlatform } from "./channelState";
import { PlatformMark } from "./PlatformMark";

export type ChannelCommand = Exclude<ChannelPrimaryAction, null> | "changeMachine" | "delete";

const PRIMARY_ICON = {
  sendTest: Send,
  reconnect: RefreshCw,
  takeBack: RefreshCw,
  retryStart: RefreshCw,
  refresh: RefreshCw,
  replaceSecret: KeyRound,
  runHere: Play,
  runHereConfirm: Play,
  turnOn: Power,
} as const;

interface Props {
  channel: ResourceOut;
  view: ChannelView;
  hasPeer: boolean;
  busy: boolean;
  onCommand: (command: ChannelCommand) => void;
}

export function ChannelDetailHeader({ channel, view, hasPeer, busy, onCommand }: Props) {
  const { t } = useTranslation();
  const words = useChannelStateWords();
  const meta = useChannelMeta(channel, view);
  const platform = channelPlatform(channel.config);
  const secretKey = platform === "telegram" ? "replaceToken" : "replaceSecret";
  const primary = view.primary;
  const PrimaryIcon = primary ? PRIMARY_ICON[primary] : null;
  const heading = channelHeading(channel);

  const actions: MenuAction[] = [
    {
      key: "sendTest",
      label: t("channels.actions.sendTestMessage"),
      disabled: !hasPeer,
      onSelect: () => onCommand("sendTest"),
    },
    {
      key: "reconnect",
      label: t("channels.actions.menu.reconnect"),
      disabled: !view.runsHere || busy,
      onSelect: () => onCommand("reconnect"),
    },
    {
      key: "changeMachine",
      label: t("channels.actions.changeMachine"),
      onSelect: () => onCommand("changeMachine"),
    },
    {
      key: "replaceSecret",
      label: t(`channels.actions.menu.${secretKey}`),
      onSelect: () => onCommand("replaceSecret"),
    },
    {
      key: "delete",
      label: t("channels.actions.menu.delete"),
      destructive: true,
      separated: true,
      onSelect: () => onCommand("delete"),
    },
  ];

  return (
    <header className="flex items-center gap-3" data-testid="channel-header">
      <PlatformMark platform={platform} size="md" className="size-8 rounded-lg" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="min-w-0 truncate text-lg font-bold">{heading}</h2>
          <StatusPill tone={view.tone}>
            <span data-testid="channel-state-word">{words(view).word}</span>
          </StatusPill>
        </div>
        <span className="truncate text-xs text-text-muted" data-testid="channel-meta">
          {meta}
        </span>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        {primary && PrimaryIcon ? (
          <Button size="sm" disabled={busy} onClick={() => onCommand(primary)}>
            <PrimaryIcon aria-hidden />
            {primary === "replaceSecret"
              ? t(`channels.actions.${secretKey}`)
              : t(`channels.actions.${primary}`)}
          </Button>
        ) : null}
        <ActionMenu label={t("channels.actions.more", { name: heading })} actions={actions} />
      </span>
    </header>
  );
}
