// src/components/chat/ThreadMessages.tsx — the rows of an open conversation, as
// wide as the content area: the persisted messages, then the prompts sent from
// here whose rows have not landed yet, then the live reply of a running turn.
// A failed-turn or lost-stream banner hangs inside the reply it belongs to (the
// live one, else the last reply if it failed or is still streaming), or inside
// a bare reply of its own when the turn left none.
import type { ReactNode } from "react";

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
  /** The banner for a failed turn or a lost stream, and which of the two it is. */
  banner?: ReactNode;
  bannerState?: "failed" | "lost";
  /** A question waits on the owner: the live reply's header says so. */
  waiting?: boolean;
  onOpenFile?: (path: string) => void;
  selectedPath?: string | null;
}

export function ThreadMessages({
  conversationId,
  agentKey,
  agentName,
  messages,
  pendingEchoes,
  live,
  notDeliveredTo,
  banner,
  bannerState,
  waiting = false,
  onOpenFile,
  selectedPath,
}: Props) {
  const last = messages.at(-1);
  const bannerOnLast =
    !!banner &&
    !live &&
    pendingEchoes.length === 0 &&
    last?.role === "assistant" &&
    (last.status === "failed" || last.status === "streaming");
  const bannerOnShell = !!banner && !live && !bannerOnLast;
  const bannerProps = { banner, bannerState };
  return (
    <div className="w-full min-w-0 space-y-5">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          undeliveredTo={notDeliveredTo(msg.id)}
          agentKey={agentKey}
          agentName={agentName}
          waiting={waiting}
          onOpenFile={onOpenFile}
          selectedPath={selectedPath}
          {...(bannerOnLast && msg === last ? bannerProps : {})}
        />
      ))}
      {pendingEchoes.map((echo) => (
        <MessageBubble key={echo.id} message={echoAsMessage(echo, conversationId)} />
      ))}
      {live && (
        <MessageBubble
          live={live}
          agentKey={agentKey}
          agentName={agentName}
          waiting={waiting}
          onOpenFile={onOpenFile}
          selectedPath={selectedPath}
          {...bannerProps}
        />
      )}
      {bannerOnShell && (
        <MessageBubble agentKey={agentKey} agentName={agentName} {...bannerProps} />
      )}
    </div>
  );
}
