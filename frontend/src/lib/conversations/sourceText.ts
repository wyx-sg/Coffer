// src/lib/conversations/sourceText.ts
// The words of a channel badge (components/sessions/SourceBadge): the platform
// and the place in its chat — "SeaTalk · DM · Thread 2",
// "SeaTalk · coffer-dev › thread", "Telegram · Personal" (the channel's name
// when the chat is not known).
import type { TFunction } from "i18next";

import type { SessionChannel } from "@/lib/sessions/rows";
import { platformName } from "@/lib/channels/platformName";

type Binding = SessionChannel;

/** "🧵#2 deploy check" → "Thread 2": the number is the mark, the title is the row's. */
function threadMark(t: TFunction, mark: string): string {
  const n = /#(\d+)/.exec(mark)?.[1];
  return n ? t("conversations.source.threadN", { n }) : t("conversations.source.thread");
}

/** The place in the chat a channel conversation lives, or null when unknown. */
function placeText(t: TFunction, binding: Binding): string | null {
  const place = binding.place;
  if (!place || !place.chat_kind) return null;
  const threadWord =
    binding.platform === "telegram"
      ? t("conversations.source.topic")
      : t("conversations.source.thread");
  if (place.chat_kind === "direct") {
    const dm = t("conversations.source.dm");
    if (place.parallel_mark) return `${dm} · ${threadMark(t, place.parallel_mark)}`;
    return place.thread ? `${dm} › ${threadWord}` : dm;
  }
  const group = place.chat_name || t("conversations.source.group");
  return place.thread ? `${group} › ${threadWord}` : group;
}

/** The badge's text, e.g. "SeaTalk · DM · Thread 2". */
export function sourceText(t: TFunction, binding: SessionChannel): string {
  const platform = binding.platform
    ? platformName(binding.platform)
    : t("conversations.source.channel");
  const where = placeText(t, binding) ?? binding.channel ?? binding.channel_uid;
  return `${platform} · ${where}`;
}
