// src/lib/chat/mirror.ts
// Pure helpers for a channel conversation's mirror (spec chat "Show where a
// reply will also be sent"): the platform's display name, and which of the
// thread's user messages the channel has not received yet.
import type { ChannelMirror, ContentBlock, Message } from "@/lib/api/chat";

/** The prefix the channel copy of a web reply carries (backend `FROM_COFFER`). */
const FROM_COFFER = "(from Coffer) ";

const PLATFORM_NAMES: Record<string, string> = { seatalk: "SeaTalk", telegram: "Telegram" };

/** A platform key as its product name (`seatalk` → `SeaTalk`). */
export function platformName(platform: string): string {
  return PLATFORM_NAMES[platform] ?? platform;
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
 * `reply` (its stored text is the message prefixed with `(from Coffer) `)
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
    const text = u.text.startsWith(FROM_COFFER) ? u.text.slice(FROM_COFFER.length) : u.text;
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
