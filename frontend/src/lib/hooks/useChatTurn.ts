// frontend/src/lib/hooks/useChatTurn.ts
// Holds a persistent GET /events subscription for the active conversation and
// accumulates SSE agent events into a live assistant message for the Chat page
// to render. The event-folding reducer lives in ./chatTurnEvents.
//
// API:
//   const { send, isStreaming, liveMessage, error, clearError,
//           interrupt, pending, setPending } = useChatTurn(convId);
//
// The subscription is opened on the active conversation and stays open across
// turns (it replays the in-flight turn then streams live). `send` is
// fire-and-return: it POSTs the message and returns immediately — the turn's
// events arrive over the subscription, not the POST.

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { subscribeConversationEvents } from "@/lib/chat/streamClient";
import { chatApi, type Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { CONVERSATIONS_KEY, messagesKey } from "./useConversations";
import { type LiveMessage, handleEvent } from "./chatTurnEvents";

export type { LiveMessage } from "./chatTurnEvents";

export interface UseChatTurnResult {
  /** Send a message to the conversation (fire-and-return; never blocks). */
  send: (text: string) => Promise<void>;
  /** True while a turn is in flight on the subscription. */
  isStreaming: boolean;
  /** Live partial message — non-null while streaming (and briefly after). */
  liveMessage: LiveMessage | null;
  /** Latest error from a failed send/stream. */
  error: Error | null;
  /** Clear any error to allow a retry. */
  clearError: () => void;
  /** Stop the in-flight turn; its partial output is kept server-side. */
  interrupt: () => Promise<void>;
  /** Queued messages waiting to run after the in-flight turn. */
  pending: string[];
  /** Replace the pending queue (resume / drop / reorder). */
  setPending: (texts: string[]) => Promise<void>;
}

export function useChatTurn(conversationId: string): UseChatTurnResult {
  const qc = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveMessage, setLiveMessage] = useState<LiveMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPendingState] = useState<string[]>([]);

  // Complete-reply count captured at turn_start (see chatTurnEvents) to detect a
  // new reply landing before dropping the live bubble. A ref so the subscription
  // effect doesn't re-run per token.
  const priorReplyCountRef = useRef(0);

  // Persistent subscription bound to the active conversation. Opened on
  // conversationId, aborted on switch/unmount. Because it replays the in-flight
  // turn and stays open across turns, no per-send stream is needed.
  useEffect(() => {
    if (!conversationId) return;

    const controller = new AbortController();
    let cancelled = false;

    setIsStreaming(false);
    setLiveMessage(null);
    setError(null);
    setPendingState([]);
    priorReplyCountRef.current = 0;

    // The SSE subscription is meant to be long-lived (it stays open across turns
    // and the server holds it open when idle). If it ENDS — a dropped connection,
    // a proxy timeout, or the server closing it — the live turn may have finished
    // server-side after we stopped receiving events, so its terminal `turn_done`
    // never reached us and the live bubble would spin on "thinking…" forever.
    // Reconcile against the persisted messages: if the reply already landed, drop
    // the stale live bubble (and leave streaming off, since the stream is gone).
    const reconcileEndedStream = async () => {
      setIsStreaming(false);
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      if (cancelled) return;
      const msgs = qc.getQueryData<Message[]>(messagesKey(conversationId)) ?? [];
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant" && last.status === "complete") {
        setLiveMessage(null);
      }
    };

    void (async () => {
      try {
        for await (const event of subscribeConversationEvents(conversationId, controller.signal)) {
          if (cancelled) return;
          await handleEvent(event, {
            conversationId,
            qc,
            priorReplyCountRef,
            setIsStreaming,
            setLiveMessage,
            setPendingState,
            setError,
            isCancelled: () => cancelled,
          });
        }
        // Stream closed cleanly (not aborted by us) — reconcile so a turn that
        // ended after the drop doesn't leave the bubble stuck on "thinking…".
        if (cancelled) return;
        await reconcileEndedStream();
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.name === "AbortError") return;
        const wrapped = err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
        await reconcileEndedStream();
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [conversationId, qc]);

  const send = useCallback(
    async (text: string) => {
      // Fire-and-return: NEVER blocks on an in-flight turn. A second message sent
      // mid-turn is queued server-side and surfaced via queue_changed.
      setError(null);
      // Optimistic echo so the prompt is visible immediately. If a turn is
      // already streaming the reply belongs to the earlier prompt, so keep the
      // existing live bubble and only fill in the echo when there is none.
      setLiveMessage(
        (prev) => prev ?? { userText: text, text: "", toolBlocks: [], streaming: false },
      );
      try {
        await chatApi.sendMessage(conversationId, text);
      } catch (err) {
        const wrapped = err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
      } finally {
        // Refresh the conversation list (first turn auto-titles it) AND the
        // messages. The messages refetch is the safety net for the draft→first-
        // send race: if the turn finished before the subscription attached (the
        // bus ring buffer is already cleared), turn_start/turn_done never fire on
        // this client, so nothing else would load the committed user message and
        // reply — leaving the optimistic echo stranded.
        void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
        void qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      }
    },
    [conversationId, qc],
  );

  const interrupt = useCallback(async () => {
    try {
      await chatApi.interruptTurn(conversationId);
    } catch {
      // Best-effort: the turn may have already finished on its own.
    }
  }, [conversationId]);

  const setPending = useCallback(
    async (texts: string[]) => {
      // Optimistic: reflect the new queue immediately; the queue_changed event
      // (or the response) reconciles it.
      setPendingState(texts);
      try {
        const res = await chatApi.setPending(conversationId, texts);
        setPendingState(res.pending);
      } catch (err) {
        const wrapped = err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
      }
    },
    [conversationId],
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    send,
    isStreaming,
    liveMessage,
    error,
    clearError,
    interrupt,
    pending,
    setPending,
  };
}
