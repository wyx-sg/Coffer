// src/lib/chat/mirror.ts
// Pure helpers for a channel conversation's mirror (spec chat "Show where a
// reply will also be sent"): the platform's display name, and which of the
// thread's user messages the channel has not received yet.
import type { ChannelMirror, ChannelPlatform, ContentBlock, Message } from "@/lib/api/chat";

/** The prefix line the channel copy of a web reply carries — `<owner> · from
 *  Coffer` and a newline (backend `mirror_target.from_coffer`). */
const FROM_COFFER = /^[^\n]* · from Coffer\n/;

const PLATFORM_NAMES: Record<ChannelPlatform, string> = {
  seatalk: "SeaTalk",
  telegram: "Telegram",
};

/** A platform key as its product name (`seatalk` → `SeaTalk`). */
export function platformName(platform: string): string {
  return PLATFORM_NAMES[platform as ChannelPlatform] ?? platform;
}

/** The text of a message's blocks, joined — what a user bubble prints. */
export function messageText(blocks: ContentBlock[]): string {
  return blocks
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text)
    .join("");
}

/**
 * The ids of the user messages the channel still owes: each undelivered
 * `reply` (its stored text is the message under the `<owner> · from Coffer` line)
 * marks the NEWEST not-yet-marked user message with the same text, so a text
 * sent twice with one copy delivered is marked once.
 */
export function undeliveredMessageIds(
  mirror: ChannelMirror | null | undefined,
  messages: Message[],
): Set<string> {
  const ids = new Set<string>();
  if (!mirror) return ids;
  const owed = new Map<string, number>();
  for (const u of mirror.undelivered) {
    if (u.kind !== "reply") continue;
    const text = u.text.replace(FROM_COFFER, "");
    owed.set(text, (owed.get(text) ?? 0) + 1);
  }
  if (owed.size === 0) return ids;
  for (const msg of [...messages].reverse()) {
    if (msg.role !== "user") continue;
    const text = messageText(msg.content);
    const n = owed.get(text) ?? 0;
    if (n > 0) {
      ids.add(msg.id);
      owed.set(text, n - 1);
    }
  }
  return ids;
}
