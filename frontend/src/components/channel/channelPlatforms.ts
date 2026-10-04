// frontend/src/components/channel/channelPlatforms.ts
// The chat platforms a channel can connect, and what each can do in a chat.
import type { ChannelType } from "@/lib/api/channels";

export const PLATFORMS: readonly ChannelType[] = ["seatalk", "telegram"];

export const CAPABILITIES: Record<string, readonly string[]> = {
  seatalk: ["privateChat", "groups", "threads", "quotes", "cards", "voice"],
  telegram: ["privateChat", "groups", "voice", "files"],
};
