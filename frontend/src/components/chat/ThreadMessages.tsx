// src/components/chat/ThreadMessages.tsx — the rows of an open conversation, in
// one readable column: the persisted messages, then the prompts sent from here
// whose rows have not landed yet, then the live reply of a running turn.
import type { Message } from "@/lib/api/chat";
import { echoAsMessage } from "@/lib/chat/echoes";
import type { LiveMessage, PendingEcho } from "@/lib/hooks/useChatTurn";
import { MessageBubble } from "./MessageBubble";

interface Props {
  conversationId: string;
  agentKey: string;
  agentName?: string;
  messages: Message[];
  pendingEchoes: PendingEcho[];
  live: LiveMessage | null;
  /** The platform a user message has not reached yet, if any. */
  notDeliveredTo: (messageId: string) => string | undefined;
}

export function ThreadMessages({
  conversationId,
  agentKey,
  agentName,
  messages,
  pendingEchoes,
  live,
  notDeliveredTo,
}: Props) {
  return (
    <div className="mx-auto w-full max-w-[720px] space-y-5">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          undeliveredTo={notDeliveredTo(msg.id)}
          agentKey={agentKey}
          agentName={agentName}
        />
      ))}
      {pendingEchoes.map((echo) => (
        <MessageBubble key={echo.id} message={echoAsMessage(echo, conversationId)} />
      ))}
      {live && <MessageBubble live={live} agentKey={agentKey} agentName={agentName} />}
    </div>
  );
}
