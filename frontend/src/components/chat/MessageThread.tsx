// components/chat/MessageThread.tsx
// Scrollable list of messages + live streaming message.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { chatApi } from "@/lib/api/chat";
import { messagesKey } from "@/lib/hooks/useConversations";
import { isNearBottom } from "@/lib/chat/scroll";
import type { LiveMessage, PendingApproval } from "@/lib/hooks/useChatTurn";
import type { Conversation } from "@/lib/api/chat";
import { Button } from "@/components/ui/button";
import { AgentModelBar } from "./AgentModelBar";
import { MessageBubble } from "./MessageBubble";
import { Composer } from "./Composer";
import { ApprovalCard } from "./ApprovalCard";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  conversation: Conversation;
  liveMessage: LiveMessage | null;
  isStreaming: boolean;
  /** Error from the latest chat turn (network, credential, agent error, etc.) */
  turnError?: Error | null;
  /** Called when the user dismisses the turn error banner. */
  onClearTurnError?: () => void;
  /** A turn paused awaiting a human allow/deny decision, if any. */
  pendingApproval?: PendingApproval | null;
  /** Called with the user's decision on the pending approval request. */
  onApprovalDecide?: (behavior: "allow" | "deny") => void | Promise<void>;
  /** Called when the user stops the in-flight turn. */
  onStop?: () => void;
  onSend: (text: string) => void;
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
  pendingApproval,
  onApprovalDecide,
  onStop,
  onSend,
  agentLabel,
  readOnly,
  onRestore,
  restorePending,
}: Props) {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Follow the stream only while the user is at the bottom; if they scroll up
  // to read history, new tokens must not yank them back down. Seeded true so
  // the first render lands at the latest message.
  const followRef = useRef(true);

  const { data, isPending, error } = useQuery({
    queryKey: messagesKey(conversation.id),
    queryFn: async () => (await chatApi.listMessages(conversation.id)).messages,
    // While the fetched history holds a streaming placeholder (a turn running
    // server-side with no client stream attached — reload / switch-back),
    // poll until it resolves so the finished reply appears without a manual
    // refresh.
    refetchInterval: (query) =>
      query.state.data?.some((m) => m.status === "streaming") ? 2000 : false,
  });

  // A persisted streaming row means a turn is in flight server-side even when
  // this client holds no stream; lock the composer (a send would just 409).
  const serverTurnActive = (data ?? []).some((m) => m.status === "streaming");
  // While the live bubble is shown, drop fetched streaming rows — a mid-turn
  // refetch (e.g. window refocus) must not duplicate the in-progress reply.
  const visibleMessages = liveMessage
    ? (data ?? []).filter((m) => m.status !== "streaming")
    : (data ?? []);

  // Optimistic echo of the just-sent prompt: shown until a refetch delivers
  // the persisted user message. Once the last fetched (non-streaming) row IS
  // that user message, the fetched row wins and the echo is suppressed.
  const echoText = liveMessage?.userText;
  const lastVisible = visibleMessages[visibleMessages.length - 1];
  const showEcho =
    echoText !== undefined &&
    !(
      lastVisible?.role === "user" &&
      lastVisible.content.some((b) => b.type === "text" && b.text === echoText)
    );

  // Auto-scroll to bottom when messages or live content changes — but only if
  // the user is already near the bottom (followRef), so reading history during
  // a stream isn't interrupted.
  useEffect(() => {
    if (followRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [data, liveMessage]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <AgentModelBar agentLabel={agentLabel} />

      <div
        ref={scrollRef}
        onScroll={() => {
          if (scrollRef.current) followRef.current = isNearBottom(scrollRef.current);
        }}
        className="flex-1 overflow-y-auto px-4 py-4"
      >
        {isPending && (
          <p className="py-8 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
        )}
        {error && (
          <p className="py-4 text-center text-sm text-destructive">{translateApiError(t, error)}</p>
        )}
        {!isPending && !error && data?.length === 0 && !liveMessage && (
          <p className="py-8 text-center text-sm text-muted-foreground">{t("chat.thread.empty")}</p>
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
          {liveMessage && <MessageBubble live={liveMessage} />}
        </div>

        <div ref={bottomRef} />
      </div>

      {/* C1: Dismissible error banner for turn/streaming failures. */}
      {turnError && (
        <div className="flex items-start gap-2 border-t border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          <span className="flex-1">{translateApiError(t, turnError)}</span>
          {onClearTurnError && (
            <button
              type="button"
              className="shrink-0 font-medium underline-offset-2 hover:underline"
              onClick={onClearTurnError}
              aria-label={t("common.dismiss")}
            >
              {t("common.dismiss")}
            </button>
          )}
        </div>
      )}

      {/* Human-approval card — shown while a turn is paused for a decision. */}
      {pendingApproval && onApprovalDecide && (
        <ApprovalCard approval={pendingApproval} onDecide={onApprovalDecide} />
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
        <Composer onSend={onSend} disabled={isStreaming || serverTurnActive} onStop={onStop} />
      )}
    </div>
  );
}
