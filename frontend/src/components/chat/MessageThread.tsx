// components/chat/MessageThread.tsx
// Messages + echoed just-sent prompts + the live message. Follows the stream
// only while the user sits at the bottom (useFollowScroll's "Jump to latest"),
// restarts at the bottom per conversation. A failed turn's banner (with a Retry
// of the failed message) and a lost stream's banner hang inside the reply they
// belong to, not above the composer. Rows are
// chosen by useMessageThread (lib/chat/threadView); the echoes are the turn hook's.
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown } from "lucide-react";
import { useMessageThread } from "@/lib/hooks/useMessageThread";
import { useFollowScroll } from "@/lib/hooks/useFollowScroll";
import { useAgentConfig, useChannelMirror } from "@/lib/hooks/useConversations";
import { useThreadQuestion } from "@/lib/hooks/useThreadQuestion";
import { describeTurnError } from "@/lib/chat/turnErrors";
import { retryTargetFor } from "@/lib/chat/threadView";
import type { PendingEcho } from "@/lib/hooks/useChatTurn";
import { Button } from "@/components/ui/button";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { ThreadMessages } from "./ThreadMessages";
import { Composer, type ComposerHandle } from "./Composer";
import type { MessageThreadProps } from "./messageThreadProps";
import { PendingQueue } from "./PendingQueue";
import { QuestionContext } from "./QuestionContext";
import { AgentModelBar } from "./AgentModelBar";
import { ArchivedNotice, StreamLostBanner } from "./ThreadNotices";
import { FindWidget } from "@/components/preview/FindWidget";
import { useDomFind } from "@/components/preview/useDomFind";
import { translateApiError } from "@/lib/api/errors";

const NO_ECHOES: PendingEcho[] = [];

export function MessageThread({
  conversation,
  liveMessage,
  pendingEchoes = NO_ECHOES,
  isStreaming,
  turnError,
  onClearTurnError,
  retryable = true,
  onResend,
  onStop,
  onSend,
  restore,
  onRestored,
  pending = [],
  onSetPending,
  queueHeld = false,
  onResumeQueue,
  agentLabel,
  streamLost = false,
  onReload,
  readOnly,
  onUnarchive,
  unarchivePending,
  onOpenFile,
  selectedPath,
}: MessageThreadProps) {
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
  // Where a reply also goes, and which ones its channel has not received yet.
  const { mirror, notDeliveredTo } = useChannelMirror(conversation, messages);
  const { data: agentConfig } = useAgentConfig(conversation.id);
  const isEmpty = messages.length === 0 && pendingEchoes.length === 0 && !liveMessage;
  // A failed turn is never "thinking": freeze the live bubble so only the
  // banner reports the state, and keep whatever text already streamed.
  const liveForRender =
    turnError && liveMessage ? { ...liveMessage, streaming: false } : liveMessage;
  // Retry re-sends the newest echo, else the last persisted user message — with
  // its attachments either way.
  const retry = retryable && !readOnly ? retryTargetFor(messages, pendingEchoes.at(-1)) : null;

  // A question waiting on the owner; text sent from the box answers it.
  const { waitingQuestion, questionActions, sendOrAnswer } = useThreadQuestion({
    conversation,
    liveMessage,
    messages,
    agentLabel,
    onSend,
  });

  const failedBanner = turnError ? (
    <ChatErrorBanner
      variant="reply"
      message={
        queueHeld && !readOnly
          ? t("conversations.queueHeld.message", { error: describeTurnError(t, turnError) })
          : t("conversations.turn.failed", { reason: describeTurnError(t, turnError) })
      }
      detail={queueHeld && !readOnly ? undefined : t("conversations.turn.failedHint")}
      onDismiss={onClearTurnError}
      retryLabel={queueHeld && !readOnly ? t("conversations.queueHeld.resume") : undefined}
      onRetry={
        queueHeld && !readOnly
          ? onResumeQueue
          : retry && (retry.kind === "send" || onResend)
            ? () => {
                onClearTurnError?.();
                void (retry.kind === "send"
                  ? onSend(retry.text, retry.attachments)
                  : onResend?.(retry.messageId));
              }
            : undefined
      }
    />
  ) : streamLost ? (
    <StreamLostBanner onReload={onReload} />
  ) : undefined;

  const scroll = useFollowScroll({
    scrollRef,
    bottomRef,
    resetKey: conversation.id,
    isStreaming,
    contentVersion: [messages, pendingEchoes, liveMessage],
  });

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="relative flex flex-1 flex-col overflow-hidden">
        <div
          ref={scrollRef}
          tabIndex={0}
          onScroll={scroll.onScroll}
          onKeyDown={onKeyDown}
          className="flex-1 overflow-y-auto px-8 py-6 outline-none"
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
              {t("conversations.thread.empty")}
            </p>
          )}

          <QuestionContext.Provider value={questionActions}>
            <ThreadMessages
              conversationId={conversation.id}
              agentKey={conversation.agent_key}
              agentName={agentLabel}
              messages={messages}
              pendingEchoes={pendingEchoes}
              live={liveForRender}
              notDeliveredTo={notDeliveredTo}
              banner={failedBanner}
              bannerState={turnError ? "failed" : streamLost ? "lost" : undefined}
              waiting={waitingQuestion !== null}
              onOpenFile={onOpenFile}
              selectedPath={selectedPath}
            />
          </QuestionContext.Provider>

          <div ref={bottomRef} />
        </div>
        {!scroll.following && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-xl shadow-overlay"
            onClick={scroll.jumpToLatest}
          >
            <ArrowDown className="mr-1 size-3.5" aria-hidden />
            {t("conversations.jumpToLatest")}
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

      {readOnly ? (
        <ArchivedNotice onUnarchive={onUnarchive} pending={unarchivePending} />
      ) : (
        <>
          <PendingQueue
            pending={pending}
            onEdit={handleEditPending}
            onRemove={(idx) => onSetPending?.(pending.filter((_, i) => i !== idx))}
          />
          {/* The composer is NEVER disabled by streaming: a message sent during a
              turn queues server-side. */}
          <Composer
            ref={composerRef}
            placeholder={t(
              waitingQuestion
                ? "conversations.question.placeholder"
                : isStreaming
                  ? "conversations.composer.queuePlaceholder"
                  : mirror
                    ? "conversations.composer.replyPlaceholder"
                    : "conversations.composer.placeholder",
              { agent: agentLabel ?? "" },
            )}
            attachmentsBlocked={waitingQuestion !== null}
            cwd={agentConfig?.cwd ?? null}
            onSend={sendOrAnswer}
            streaming={isStreaming}
            onStop={onStop}
            restore={restore}
            onRestored={onRestored}
            controls={
              <AgentModelBar
                conversationId={conversation.id}
                agentKey={conversation.agent_key}
                agentLabel={agentLabel}
              />
            }
          />
        </>
      )}
    </div>
  );
}
