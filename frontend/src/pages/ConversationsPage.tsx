// pages/ConversationsPage.tsx — spec chat "Show channel conversations on the
// Conversations page". `/conversations` is a list and nothing else: the
// conversations IM channels (SeaTalk, Telegram) opened, filtered by search,
// channel and agent in the URL. There is no conversation view, no reply box and
// no New conversation. Pressing a row has no action yet: `onPrimaryAction` is
// the slot where a row opens its session in a terminal.
import { ConversationsIndex } from "@/components/conversations/ConversationsIndex";

export function ConversationsPage() {
  return <ConversationsIndex />;
}
