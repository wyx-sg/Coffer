// frontend/src/components/workflow/NodeThread.tsx
// One task's conversation — and, since a run has none of its own (FR-030),
// the only conversation there is.
//
// A node opens with its bound skill already driving it, so the ordinary case
// is that nobody types here at all. The composer exists for the other case:
// the requirement changed, and the developer says so in ordinary words rather
// than through a form. What they say stays in this transcript, which is what
// every later task opens with (FR-029) — so a redirect stated once reaches the
// rest of the run without being restated.
//
// The conversation is an ORDINARY Coffer conversation, so the chat layer owns
// it end to end: `useMessageThread` for the rows and `MessageBubble` for each
// one. A second message renderer for workflow messages would be a second chat.
//
// The TURN is handed in rather than started here: the composer sits below this
// panel and the panel beside it, because what you type is addressed to the
// task and not to one column of it. Send, stop and "is it streaming" are one
// state, so they live where the composer is.
import { useTranslation } from "react-i18next";

import type { Message } from "@/lib/api/chat";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { ChatErrorBanner } from "@/components/chat/ChatErrorBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { NodeApprovals } from "@/components/workflow/NodeApprovals";
import { describeTurnError } from "@/lib/chat/turnErrors";
import { translateApiError } from "@/lib/api/errors";
import type { PendingEcho, UseChatTurnResult } from "@/lib/hooks/useChatTurn";
import { useMessageThread } from "@/lib/hooks/useMessageThread";

/** Shape a just-sent prompt as a user message so MessageBubble renders it. */
function echoAsMessage(echo: PendingEcho, conversationId: string): Message {
  return {
    id: echo.id,
    conversation_id: conversationId,
    seq: Number.MAX_SAFE_INTEGER,
    role: "user",
    content: [{ type: "text", text: echo.text }],
    status: "complete",
    created_at: new Date(echo.sentAt).toISOString(),
  };
}

interface Props {
  conversationId: string;
  runId: string;
  /** The attempt whose approvals belong in this thread (FR-039). */
  attemptId: string | null | undefined;
  /** The live turn, owned by the workspace because the composer is. */
  turn: UseChatTurnResult;
}

export function NodeThread({ conversationId, runId, attemptId, turn }: Props) {
  const { t } = useTranslation();
  const { messages, isPending, error } = useMessageThread(
    conversationId,
    turn.liveMessage,
    turn.error,
  );
  const isEmpty = messages.length === 0 && turn.pendingEchoes.length === 0 && !turn.liveMessage;

  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-label={t("workflow.nodeConversation.threadLabel")}
    >
      <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
        {isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : error ? (
          <p className="text-sm text-destructive">{translateApiError(t, error)}</p>
        ) : isEmpty ? (
          <p className="text-sm text-muted-foreground">
            {t("workflow.nodeConversation.threadEmpty")}
          </p>
        ) : (
          messages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
        {turn.pendingEchoes.map((echo) => (
          <MessageBubble key={echo.id} message={echoAsMessage(echo, conversationId)} />
        ))}
        {/* A failed turn is never "thinking": freeze the bubble so only the
            banner reports the state, and keep whatever text already streamed. */}
        {turn.liveMessage ? (
          <MessageBubble
            live={turn.error ? { ...turn.liveMessage, streaming: false } : turn.liveMessage}
          />
        ) : null}

        {/* Last in the scroll region: an approval is the newest thing that
            happened, and it is read where the developer already is. Renders
            nothing when there is nothing waiting. */}
        <NodeApprovals runId={runId} attemptId={attemptId} />
      </div>

      {turn.error ? (
        <ChatErrorBanner
          className="border-t"
          message={describeTurnError(t, turn.error)}
          onDismiss={turn.clearError}
        />
      ) : null}
    </section>
  );
}
