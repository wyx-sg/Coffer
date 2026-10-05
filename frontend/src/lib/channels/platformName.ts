// src/lib/channels/platformName.ts — a chat platform key as its product name.
import type { ChannelPlatform } from "@/lib/api/chat";

const PLATFORM_NAMES: Record<ChannelPlatform, string> = {
  seatalk: "SeaTalk",
  telegram: "Telegram",
};

/** A platform key as its product name (`seatalk` → `SeaTalk`). */
export function platformName(platform: string): string {
  return PLATFORM_NAMES[platform as ChannelPlatform] ?? platform;
}
