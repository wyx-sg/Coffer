// frontend/src/components/channel/channelLabels.ts
// How a channel reads on screen: "SeaTalk · Team bot" as its heading, the
// word and the list line for its state, the machine it runs on by name, and
// the meta line under the header. One module so the list row and the header
// say the same thing about the same channel.
import { useTranslation } from "react-i18next";

import type { ResourceOut } from "@/lib/api/resources";
import type { ChannelView } from "@/lib/channels/channelState";
import { channelPlatform } from "@/lib/channels/channelState";
import { platformLabel } from "./PlatformMark";

/** "SeaTalk · Team bot" — the platform, then the name the person chose. */
export function channelHeading(channel: ResourceOut): string {
  return `${platformLabel(channelPlatform(channel.config))} · ${channel.name}`;
}

/** The state's status word and its list line. */
export function useChannelStateWords(): (view: ChannelView) => { word: string; line: string } {
  const { t } = useTranslation();
  return (view) => ({
    word: t(`channels.state.${view.state}.word`),
    line: t(`channels.state.${view.state}.line`),
  });
}

/** "SeaTalk app 8231 · WebSocket" / "@bot · long polling · …":
 *  the platform's identity and transport, then "off" when it is switched off. */
export function useChannelMeta(channel: ResourceOut, view: ChannelView): string {
  const { t } = useTranslation();
  const platform = channelPlatform(channel.config);
  const appId = typeof channel.config.app_id === "string" ? channel.config.app_id : "";
  const seatalk = platform === "seatalk";
  const transport =
    seatalk && view.state === "notPaired"
      ? t("channels.meta.websocketConnected")
      : seatalk
        ? t("channels.meta.websocket")
        : t("channels.meta.longPolling");
  const parts = seatalk ? [t("channels.meta.seatalkApp", { appId }), transport] : [transport];
  if (view.state === "off") parts.push(t("channels.meta.off"));
  return parts.join(" · ");
}

/** Why Send test is greyed out in this state; null when it can be pressed.
 *  Only a connected, paired channel can send one. */
export function useSendTestBlockedReason(channel: ResourceOut, view: ChannelView): string | null {
  const { t } = useTranslation();
  if (view.state === "connected") return null;
  const secret = channelPlatform(channel.config) === "telegram" ? "token" : "secret";
  switch (view.state) {
    case "connectFailed":
    case "stopped":
      return t(`channels.header.sendTestWhy.replace_${secret}`);
    case "approvalRefused":
      return t("channels.header.sendTestWhy.waitingApproval");
    case "connecting":
    case "unreachable":
    case "loading":
      return t("channels.header.sendTestWhy.reconnecting");
    default:
      return t(`channels.header.sendTestWhy.${view.state}`);
  }
}
