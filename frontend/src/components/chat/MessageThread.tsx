// components/chat/MessageThread.tsx
// Scrollable list of messages + echoed just-sent prompts + live streaming
// message. Follows the stream only while the user sits at the bottom (a "Jump
// to latest" pill brings them back — useFollowScroll), restarts at the bottom
// whenever another conversation opens, and on a failed turn swaps the
// in-progress bubble for the error banner with a Retry that re-sends the
// message that failed. Which persisted rows render is decided by
// useMessageThread (lib/chat/threadView); the echoes are the turn hook's.
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown } from "lucide-react";
import { useMessageThread } from "@/lib/hooks/useMessageThread";
import { useFollowScroll } from "@/lib/hooks/useFollowScroll";
import { describeTurnError } from "@/lib/chat/turnErrors";
import { retryTextFor } from "@/lib/chat/threadView";
import type { LiveMessage, PendingEcho } from "@/lib/hooks/useChatTurn";
import type { Conversation, Message } from "@/lib/api/chat";
import { Button } from "@/components/ui/button";
import { AgentModelBar } from "./AgentModelBar";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { MessageBubble } from "./MessageBubble";
import { Composer, type ComposerHandle } from "./Composer";
import { PendingQueue } from "./PendingQueue";
import { FindWidget } from "@/components/preview/FindWidget";
import { useDomFind } from "@/components/preview/useDomFind";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  conversation: Conversation;
  liveMessage: LiveMessage | null;
  /**
   * Prompts sent from this client whose persisted rows have not landed yet.
   * Rendered as user bubbles after the fetched messages; the turn hook owns
   * when each one retires, so the thread never dedupes them itself.
   */
  pendingEchoes?: PendingEcho[];
  isStreaming: boolean;
  /** Error from the latest chat turn (network, credential, agent error, etc.) */
  turnError?: Error | null;
  /** Called when the user dismisses the turn error banner. */
  onClearTurnError?: () => void;
  /** Called when the user stops the in-flight turn. */
  onStop?: () => void;
  onSend: (text: string) => void;
  /** Messages queued behind the in-flight turn. */
  pending?: string[];
  /** Replace the pending queue (used to remove a queued message). */
  onSetPending?: (texts: string[]) => void;
  /** Display name of the conversation's agent (from the agents API). */
  agentLabel?: string;
  /** Render read-only (archived conversation): restore CTA instead of composer. */
  readOnly?: boolean;
  /** Called when the user restores the archived conversation. */
  onRestore?: () => void;
  /** True while the restore request is in flight. */
  restorePending?: boolean;
}

const NO_ECHOES: PendingEcho[] = [];

/** Shape an echo as a user message so MessageBubble renders it like a row. */
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

export function MessageThread({
  conversation,
  liveMessage,
  pendingEchoes = NO_ECHOES,
  isStreaming,
  turnError,
  onClearTurnError,
  onStop,
  onSend,
  pending = [],
  onSetPending,
  agentLabel,
  readOnly,
  onRestore,
  restorePending,
}: Props) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<ComposerHandle>(null);

  // Edit a queued message: pull it out of the queue and back into the composer
  // for the user to amend. Re-sending it goes through the normal send path, so a
  // still-streaming turn re-queues it at the tail.
  const handleEditPending = (idx: number) => {
    const text = pending[idx];
    if (text === undefined) return;
    onSetPending?.(pending.filter((_, i) => i !== idx));
    composerRef.current?.setText(text);
  };
  // Transcript-wide Cmd/Ctrl+F over the rendered messages (shared find UX).
  const { find, inputRef, onKeyDown } = useDomFind(scrollRef);

  const { messages, isPending, error } = useMessageThread(conversation.id, liveMessage, turnError);
  const isEmpty = messages.length === 0 && pendingEchoes.length === 0 && !liveMessage;
  // A failed turn is never "thinking": freeze the live bubble so only the
  // banner reports the state, and keep whatever text already streamed.
  const liveForRender =
    turnError && liveMessage ? { ...liveMessage, streaming: false } : liveMessage;
  // Retry re-sends the newest echo, else the last persisted user message.
  const retryText = retryTextFor(messages, pendingEchoes[pendingEchoes.length - 1]?.text);

  const scroll = useFollowScroll({
    scrollRef,
    bottomRef,
    resetKey: conversation.id,
    isStreaming,
    contentVersion: [messages, pendingEchoes, liveMessage],
  });

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <AgentModelBar
        conversationId={conversation.id}
        agentKey={conversation.agent_key}
        agentLabel={agentLabel}
        disabled={readOnly}
      />

      <div className="relative flex flex-1 flex-col overflow-hidden">
        <div
          ref={scrollRef}
          tabIndex={0}
          onScroll={scroll.onScroll}
          onKeyDown={onKeyDown}
          className="flex-1 overflow-y-auto px-4 py-4 outline-none"
        >
          {isPending && (
            <p className="py-8 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
          )}
          {error && (
            <p className="py-4 text-center text-sm text-destructive">
              {translateApiError(t, error)}
            </p>
          )}
          {!isPending && !error && isEmpty && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {t("chat.thread.empty")}
            </p>
          )}

          <div className="space-y-3">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {pendingEchoes.map((echo) => (
              <MessageBubble key={echo.id} message={echoAsMessage(echo, conversation.id)} />
            ))}
            {liveForRender && <MessageBubble live={liveForRender} />}
          </div>

          <div ref={bottomRef} />
        </div>
        {!scroll.following && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-xl shadow-md"
            onClick={scroll.jumpToLatest}
          >
            <ArrowDown className="mr-1 size-3.5" aria-hidden />
            {t("chat.jumpToLatest")}
          </Button>
        )}
        {find.open ? (
          <FindWidget
            ref={inputRef}
            query={find.query}
            count={find.count}
            active={find.active}
            caseSensitive={find.caseSensitive}
            onQueryChange={find.setQuery}
            onToggleCase={find.toggleCaseSensitive}
            onNext={find.next}
            onPrev={find.prev}
            onClose={find.closeFind}
          />
        ) : null}
      </div>

      {turnError && (
        <ChatErrorBanner
          className="border-t"
          message={describeTurnError(t, turnError)}
          onDismiss={onClearTurnError}
          onRetry={
            retryText && !readOnly
              ? () => {
                  onClearTurnError?.();
                  onSend(retryText);
                }
              : undefined
          }
        />
      )}

      {readOnly ? (
        // Archived conversations are read-only — restoring re-enables chat.
        <div className="flex items-center justify-between gap-3 border-t border-border bg-card px-4 py-3">
          <span className="text-sm text-muted-foreground">{t("chat.archivedThread.notice")}</span>
          <Button size="sm" onClick={onRestore} disabled={restorePending || !onRestore}>
            {restorePending ? t("chat.archivedThread.restoring") : t("chat.archivedThread.restore")}
          </Button>
        </div>
      ) : (
        <>
          <PendingQueue
            pending={pending}
            onEdit={handleEditPending}
            onRemove={(idx) => onSetPending?.(pending.filter((_, i) => i !== idx))}
          />
          {/* The composer is NEVER disabled by streaming: a message sent during a
              turn queues server-side. */}
          <Composer ref={composerRef} onSend={onSend} streaming={isStreaming} onStop={onStop} />
        </>
      )}
    </div>
  );
}
