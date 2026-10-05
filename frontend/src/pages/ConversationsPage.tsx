// pages/ConversationsPage.tsx — spec chat "Show every agent's sessions on the
// Conversations page". `/conversations` lists every session of every agent,
// wherever it was started, filtered by search, source and agent in the URL; its
// header starts a New conversation. There is no conversation view and no reply
// box. Pressing a row opens its session in the preferred terminal.
import { ConversationsIndex } from "@/components/conversations/ConversationsIndex";

export function ConversationsPage() {
  return <ConversationsIndex />;
}
