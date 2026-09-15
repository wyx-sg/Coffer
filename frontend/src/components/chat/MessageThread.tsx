// components/chat/MessageThread.tsx
// Scrollable list of messages + live streaming message. Follows the stream
// only while the user sits at the bottom (a "Jump to latest" pill brings them
// back — useFollowScroll), restarts at the bottom whenever another
// conversation opens, and on a failed turn swaps the in-progress bubble for the
// error banner with a Retry that re-sends the message that failed. Which rows
// render is decided by the pure helpers in lib/chat/threadView.
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";
import { chatApi } from "@/lib/api/chat";
import { messagesKey } from "@/lib/hooks/useConversations";
import { useFollowScroll } from "@/lib/hooks/useFollowScroll";
import { describeTurnError } from "@/lib/chat/turnErrors";
import { retryTextFor, shouldShowEcho, visibleThreadMessages } from "@/lib/chat/threadView";
import type { LiveMessage } from "@/lib/hooks/useChatTurn";
import type { Conversation } from "@/lib/api/chat";
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

export function MessageThread({
  conversation,
  liveMessage,
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

  const { data, isPending, error } = useQuery({
    queryKey: messagesKey(conversation.id),
    queryFn: async () => (await chatApi.listMessages(conversation.id)).messages,
    // No polling: the persistent /events subscription drives the live turn and
    // invalidates this query when the turn ends.
  });

  const visibleMessages = visibleThreadMessages(data ?? [], liveMessage, turnError);
  const echoText = liveMessage?.userText;
  const showEcho = shouldShowEcho(visibleMessages, echoText);
  // A failed turn is never "thinking": freeze the live bubble so only the
  // banner reports the state, and keep whatever text already streamed.
  const liveForRender =
    turnError && liveMessage ? { ...liveMessage, streaming: false } : liveMessage;
  const retryText = retryTextFor(visibleMessages, echoText);

  const scroll = useFollowScroll({
    scrollRef,
    bottomRef,
    resetKey: conversation.id,
    isStreaming,
    contentVersion: [data, liveMessage],
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
          {!isPending && !error && data?.length === 0 && !liveMessage && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {t("chat.thread.empty")}
            </p>
          )}

          <div className="space-y-3">
            {visibleMessages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {showEcho && (
              <MessageBubble
                message={{
                  id: "optimistic-user-echo",
                  conversation_id: conversation.id,
                  seq: Number.MAX_SAFE_INTEGER,
                  role: "user",
                  content: [{ type: "text", text: echoText }],
                  status: "complete",
                  created_at: "",
                }}
              />
            )}
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
