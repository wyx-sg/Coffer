// frontend/src/components/channel/channelLabels.ts
// How a channel reads on screen: "SeaTalk · Team bot" as its heading, the
// word and the list line for its state, the machine it runs on by name, and
// the meta line under the header. One module so the list row and the header
// say the same thing about the same channel.
import { useTranslation } from "react-i18next";

import type { ResourceOut } from "@/lib/api/resources";
import { useMachines, useThisMachineId } from "@/lib/hooks/useMachines";
import { machineOptionFor } from "@/lib/machineBinding";
import { displayName } from "@/lib/resourceTitle";
import type { ChannelView } from "@/lib/channels/channelState";
import { channelPlatform } from "@/lib/channels/channelState";
import { platformLabel } from "./PlatformMark";

/** "SeaTalk · Team bot" — the platform, then the name the person chose. */
export function channelHeading(channel: ResourceOut): string {
  return `${platformLabel(channelPlatform(channel.config))} · ${displayName(channel)}`;
}

/** A machine id as the person knows it: its registry name, "this machine",
 *  or a shortened id for one nobody claims. */
export function useMachineName(): (id: string | null) => string {
  const { t } = useTranslation();
  const { data } = useMachines();
  const { machineId: selfId } = useThisMachineId();
  return (id) => {
    if (id === null) return t("channels.machine.unbound");
    const option = machineOptionFor(data?.machines ?? [], selfId, id);
    if (option.isSelf) return t("channels.machine.thisMachine");
    if (option.name) return option.name;
    return id.length > 12 ? `${id.slice(0, 5)}…${id.slice(-2)}` : id;
  };
}

/** The state's status word and its list line, with the machine filled in. */
export function useChannelStateWords(): (view: ChannelView) => { word: string; line: string } {
  const { t } = useTranslation();
  const machineName = useMachineName();
  return (view) => {
    const machine = machineName(view.runsOn);
    return {
      word: t(`channels.state.${view.state}.word`, { machine }),
      line: t(`channels.state.${view.state}.line`, { machine }),
    };
  };
}

/** "SeaTalk app 8231 · WebSocket · runs on this Mac" / "@bot · long polling · …":
 *  the platform's identity and transport, then where it runs — or why it does not. */
export function useChannelMeta(channel: ResourceOut, view: ChannelView): string {
  const { t } = useTranslation();
  const machineName = useMachineName();
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
  else if (view.state === "unbound" || view.state === "unknownMachine")
    parts.push(t("channels.meta.unknownMachine"));
  else if (view.state === "elsewhere")
    parts.push(t("channels.meta.runsOn", { machine: machineName(view.runsOn) }));
  else if (view.runsHere) parts.push(t("channels.meta.runsHere"));
  return parts.join(" · ");
}

/** Why Send test is greyed out in this state; null when it can be pressed.
 *  Only a connected, paired channel can send one. */
export function useSendTestBlockedReason(channel: ResourceOut, view: ChannelView): string | null {
  const { t } = useTranslation();
  const machineName = useMachineName();
  if (view.state === "connected") return null;
  const secret = channelPlatform(channel.config) === "telegram" ? "token" : "secret";
  switch (view.state) {
    case "connectFailed":
    case "stopped":
      return t(`channels.header.sendTestWhy.replace_${secret}`);
    case "elsewhere":
      return t("channels.header.sendTestWhy.elsewhere", { machine: machineName(view.runsOn) });
    case "unbound":
    case "unknownMachine":
      return t("channels.header.sendTestWhy.unbound");
    case "approvalRefused":
      return t("channels.header.sendTestWhy.waitingApproval");
    case "connecting":
    case "loading":
      return t("channels.header.sendTestWhy.reconnecting");
    default:
      return t(`channels.header.sendTestWhy.${view.state}`);
  }
}
