// frontend/src/components/channel/ChannelDetailHeader.tsx
// The top of the open channel (board 3.2.01): its platform mark, "SeaTalk ·
// Team bot", the status pill, one meta line (app id, transport, where it
// runs), and on the right the same two controls in every state — a secondary
// Send test and a ⋯ menu holding only Reconnect. Nothing here changes with the
// state: when Send test cannot go, it is greyed out and its tooltip says why;
// the fix for a problem is in the banner under the header.
import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";

import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ResourceOut } from "@/lib/api/resources";
import {
  channelHeading,
  useChannelMeta,
  useChannelStateWords,
  useSendTestBlockedReason,
} from "./channelLabels";
import type { ChannelPrimaryAction, ChannelView } from "@/lib/channels/channelState";
import { channelPlatform } from "@/lib/channels/channelState";
import { PlatformMark } from "./PlatformMark";

/** What a banner button, the grey box or the header can ask the pane to do. */
export type ChannelCommand = Exclude<ChannelPrimaryAction, null> | "sendTest";

/** States in which there is nothing to reconnect: the channel is off, or its
 *  status is not known yet. */
const NO_RECONNECT = new Set(["off", "loading"]);

interface Props {
  channel: ResourceOut;
  view: ChannelView;
  busy: boolean;
  onCommand: (command: ChannelCommand) => void;
}

export function ChannelDetailHeader({ channel, view, busy, onCommand }: Props) {
  const { t } = useTranslation();
  const words = useChannelStateWords();
  const meta = useChannelMeta(channel, view);
  const blocked = useSendTestBlockedReason(channel, view);
  const platform = channelPlatform(channel.config);
  const heading = channelHeading(channel);

  // Reconnect stays in the menu in every state; it is disabled, not hidden,
  // when there is no connection of this Mac's to restart.
  const actions: MenuAction[] = [
    {
      key: "reconnect",
      label: t("channels.actions.menu.reconnect"),
      disabled: NO_RECONNECT.has(view.state) || busy,
      onSelect: () => onCommand("reconnect"),
    },
  ];

  const sendTest = (
    <Button
      variant="outline"
      size="sm"
      disabled={blocked !== null}
      onClick={() => onCommand("sendTest")}
    >
      <Send aria-hidden />
      {t("channels.actions.sendTest")}
    </Button>
  );

  return (
    <header className="flex items-center gap-3" data-testid="channel-header">
      <PlatformMark platform={platform} size="md" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex min-h-7 min-w-0 items-center gap-2.5">
          <h2 className="min-w-0 truncate text-lg font-[650]">{heading}</h2>
          <StatusPill tone={view.tone}>
            <span data-testid="channel-state-word">{words(view).word}</span>
          </StatusPill>
        </div>
        <span className="truncate text-sm text-text-muted" data-testid="channel-meta">
          {meta}
        </span>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        {blocked !== null ? (
          <Tooltip>
            <TooltipTrigger asChild>
              {/* A disabled button gets no pointer events; its wrapper carries the tooltip. */}
              <span tabIndex={0} className="inline-flex cursor-not-allowed">
                {sendTest}
              </span>
            </TooltipTrigger>
            <TooltipContent>{blocked}</TooltipContent>
          </Tooltip>
        ) : (
          sendTest
        )}
        <ActionMenu label={t("channels.actions.more")} actions={actions} />
      </span>
    </header>
  );
}
