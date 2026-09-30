// frontend/src/components/channel/channelPlatforms.ts
// The chat platforms a channel can connect, what each can do in a chat, and
// the words a platform card is matched against by the add dialog's filter.
import { useTranslation } from "react-i18next";

import type { ChannelType } from "@/lib/api/channels";
import { platformLabel } from "./PlatformMark";

export const PLATFORMS: readonly ChannelType[] = ["seatalk", "telegram"];

export const CAPABILITIES: Record<string, readonly string[]> = {
  seatalk: ["privateChat", "groups", "threads", "quotes", "cards", "voice"],
  telegram: ["privateChat", "groups", "voice", "files"],
};

/** The words a card is matched against by the add dialog's filter. */
export function usePlatformSearchText(): (platform: ChannelType) => string {
  const { t } = useTranslation();
  return (platform) =>
    [
      platformLabel(platform),
      t(`channels.platforms.${platform}.body`),
      ...(CAPABILITIES[platform] ?? []).map((c) => t(`channels.platforms.capabilities.${c}`)),
    ]
      .join(" ")
      .toLowerCase();
}
