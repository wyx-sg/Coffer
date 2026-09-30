// components/chat/MessageThread.tsx
// Messages + echoed just-sent prompts + the live message. Follows the stream
// only while the user sits at the bottom (useFollowScroll's "Jump to latest"),
// restarts at the bottom per conversation, and on a failed turn swaps the live
// bubble for the error banner with a Retry of the failed message. Rows are
// chosen by useMessageThread (lib/chat/threadView); the echoes are the turn hook's.
import { useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown } from "lucide-react";
import { useMessageThread } from "@/lib/hooks/useMessageThread";
import { useFollowScroll } from "@/lib/hooks/useFollowScroll";
import { useChannelMirror } from "@/lib/hooks/useConversations";
import { describeTurnError } from "@/lib/chat/turnErrors";
import { retryTargetFor } from "@/lib/chat/threadView";
import type { LiveMessage, PendingEcho } from "@/lib/hooks/useChatTurn";
import type { EchoAttachment } from "@/lib/chat/echoes";
import type { Conversation } from "@/lib/api/chat";
import { Button } from "@/components/ui/button";
import { ChannelMirrorHint } from "./ChannelMirrorHint";
import { ChatErrorBanner } from "./ChatErrorBanner";
import { ThreadMessages } from "./ThreadMessages";
import { Composer, type ComposerHandle } from "./Composer";
import type { ComposerRestore } from "@/lib/hooks/useComposerRestore";
import { PendingQueue } from "./PendingQueue";
import { ArchivedNotice, StreamLostBanner } from "./ThreadNotices";
import { FindWidget } from "@/components/preview/FindWidget";
import { useDomFind } from "@/components/preview/useDomFind";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  conversation: Conversation;
  liveMessage: LiveMessage | null;
  /** Prompts sent from here whose rows have not landed yet (the turn hook retires them). */
  pendingEchoes?: PendingEcho[];
  isStreaming: boolean;
  /** Error from the latest turn (network, secret, agent error, …), and its dismiss. */
  turnError?: Error | null;
  onClearTurnError?: () => void;
  /** False when turnError is a refused send (it stays in the composer): no Retry. */
  retryable?: boolean;
  /** Send a persisted user message again, attachments included (Retry). */
  onResend?: (messageId: string) => void | Promise<boolean>;
  onStop?: () => void;
  /** Send a message with the finished uploads; resolves whether it was accepted. */
  onSend: (text: string, attachments?: EchoAttachment[]) => void | Promise<boolean>;
  /** A refused message handed back to the composer (see Composer `restore`). */
  restore?: ComposerRestore | null;
  onRestored?: () => void;
  /** Messages queued behind the in-flight turn, and its replacement (edit / remove). */
  pending?: string[];
  onSetPending?: (texts: string[]) => void;
  /** The conversation's header (title, source, agent / model / effort, menu). */
  header?: ReactNode;
  /** Display name of the conversation's agent — the composer's placeholder. */
  agentLabel?: string;
  /** The live stream was lost mid-turn after every reconnect: say so, offer Reload. */
  streamLost?: boolean;
  onReload?: () => void;
  /** Archived: read-only, a Restore in place of the composer. */
  readOnly?: boolean;
  onRestore?: () => void;
  restorePending?: boolean;
}

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
  header,
  agentLabel,
  streamLost = false,
  onReload,
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
  // Where a reply also goes, and which ones its channel has not received yet.
  const { mirror, notDeliveredTo } = useChannelMirror(conversation, messages);
  const isEmpty = messages.length === 0 && pendingEchoes.length === 0 && !liveMessage;
  // A failed turn is never "thinking": freeze the live bubble so only the
  // banner reports the state, and keep whatever text already streamed.
  const liveForRender =
    turnError && liveMessage ? { ...liveMessage, streaming: false } : liveMessage;
  // Retry re-sends the newest echo, else the last persisted user message — with
  // its attachments either way.
  const retry = retryable && !readOnly ? retryTargetFor(messages, pendingEchoes.at(-1)) : null;

  const scroll = useFollowScroll({
    scrollRef,
    bottomRef,
    resetKey: conversation.id,
    isStreaming,
    contentVersion: [messages, pendingEchoes, liveMessage],
  });

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {header}

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

          <ThreadMessages
            conversationId={conversation.id}
            agentKey={conversation.agent_key}
            agentName={agentLabel}
            messages={messages}
            pendingEchoes={pendingEchoes}
            live={liveForRender}
            notDeliveredTo={notDeliveredTo}
          />

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

      {streamLost && !turnError && <StreamLostBanner onReload={onReload} />}

      {turnError && (
        <ChatErrorBanner
          className="border-t"
          message={describeTurnError(t, turnError)}
          onDismiss={onClearTurnError}
          onRetry={
            retry && (retry.kind === "send" || onResend)
              ? () => {
                  onClearTurnError?.();
                  void (retry.kind === "send"
                    ? onSend(retry.text, retry.attachments)
                    : onResend?.(retry.messageId));
                }
              : undefined
          }
        />
      )}

      {readOnly ? (
        <ArchivedNotice onRestore={onRestore} pending={restorePending} />
      ) : (
        <>
          <PendingQueue
            pending={pending}
            onEdit={handleEditPending}
            onRemove={(idx) => onSetPending?.(pending.filter((_, i) => i !== idx))}
          />
          {mirror && <ChannelMirrorHint mirror={mirror} />}
          {/* The composer is NEVER disabled by streaming: a message sent during a
              turn queues server-side. */}
          <Composer
            ref={composerRef}
            placeholder={t(
              isStreaming
                ? "conversations.composer.queuePlaceholder"
                : mirror
                  ? "conversations.composer.replyPlaceholder"
                  : "conversations.composer.placeholder",
              { agent: agentLabel ?? "" },
            )}
            onSend={onSend}
            streaming={isStreaming}
            onStop={onStop}
            restore={restore}
            onRestored={onRestored}
          />
        </>
      )}
    </div>
  );
}
