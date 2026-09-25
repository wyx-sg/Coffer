// frontend/src/lib/hooks/useChatTurn.ts
// Holds a persistent GET /events subscription for the active conversation and
// accumulates SSE agent events into a live assistant message for the Chat page
// to render. The event-folding reducer lives in ./chatTurnEvents.
//
// API:
//   const { send, resend, isStreaming, liveMessage, pendingEchoes, error,
//           retryable, clearError, interrupt, pending, setPending } = useChatTurn(convId);
//
// The subscription is opened on the active conversation and stays open across
// turns (it replays the in-flight turn then streams live). `send` and `resend`
// (./useChatSend) are fire-and-return: they POST and return immediately — the
// turn's events arrive over the subscription, not the POST.

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { subscribeConversationEvents } from "@/lib/chat/streamClient";
import { chatApi, type Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { messagesKey } from "@/lib/api/queryKeys";
import { type EchoAttachment, type PendingEcho, reconcileEchoes } from "@/lib/chat/echoes";
import { type LiveMessage, handleEvent, subscribeMessagesCache } from "./chatTurnEvents";
import { useChatSend } from "./useChatSend";

export type { LiveMessage } from "./chatTurnEvents";
export type { PendingEcho } from "@/lib/chat/echoes";

// A mid-turn stream drop is recovered by re-subscribing (GET /events replays the
// in-flight turn), bounded so a hard failure can't hammer the endpoint.
const MAX_STREAM_RECONNECTS = 5;
const RECONNECT_BACKOFF_MS = 300;

export interface UseChatTurnResult {
  /**
   * Send a message to the conversation (fire-and-return; never blocks), with the
   * composer's finished uploads. Resolves whether the daemon accepted it; a
   * refusal is also surfaced as `error`.
   */
  send: (text: string, attachments?: EchoAttachment[]) => Promise<boolean>;
  /** Send a persisted user message again, attachments included (Retry). */
  resend: (messageId: string) => Promise<boolean>;
  /** True while a turn is in flight on the subscription. */
  isStreaming: boolean;
  /** Live partial message — non-null while streaming (and briefly after). */
  liveMessage: LiveMessage | null;
  /**
   * Prompts this client sent whose persisted user rows have not been fetched
   * yet, in send order. The thread renders them after the fetched messages;
   * the hook retires each one when its row lands (see chatTurnEvents).
   */
  pendingEchoes: PendingEcho[];
  /** Latest error from a failed send/stream. */
  error: Error | null;
  /**
   * False when `error` is a refused send: that message never ran and stays in
   * the composer, so a Retry would re-send an older one.
   */
  retryable: boolean;
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
  const [echoes, setEchoes] = useState<PendingEcho[]>([]);
  // The last error that was a refused POST rather than a failed turn.
  const [refused, setRefused] = useState<Error | null>(null);

  // Mirror of isStreaming for send(): a message sent while a turn is in flight
  // is queued server-side and shown by the queue chip, so it gets no echo.
  const isStreamingRef = useRef(false);
  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  // Retire echoes as their persisted rows land — on every fill of the messages
  // cache (turn_start / turn_done / send refetches, window refocus, ...).
  useEffect(() => {
    if (!conversationId) return;
    return subscribeMessagesCache(qc, conversationId, (rows) => {
      setEchoes((prev) => reconcileEchoes(prev, rows));
    });
  }, [conversationId, qc]);

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
    setEchoes([]);
    priorReplyCountRef.current = 0;

    // Reconcile against the persisted messages once the stream ends. Returns
    // true when the turn has SETTLED server-side (its reply is committed), so the
    // caller can drop the stale live bubble; false when no reply has landed (the
    // turn may still be running after a mid-turn drop).
    const replyHasLanded = async (): Promise<boolean> => {
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      if (cancelled) return true;
      const msgs = qc.getQueryData<Message[]>(messagesKey(conversationId)) ?? [];
      const last = msgs[msgs.length - 1];
      return last?.role === "assistant" && last.status === "complete";
    };

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, ms);
        controller.signal.addEventListener(
          "abort",
          () => {
            clearTimeout(timer);
            resolve();
          },
          { once: true },
        );
      });

    // The SSE subscription is meant to be long-lived (it stays open across turns
    // and the server holds it open when idle). If it ENDS mid-turn — a dropped
    // connection, a proxy timeout, or the server closing it — the terminal
    // `turn_done` may never reach us and the live bubble would spin on
    // "thinking…" forever (the reply only surfaces when the next send refetches
    // messages). Recover by RE-SUBSCRIBING: GET /events replays the in-flight
    // turn on reattach, so the missed events (including `turn_done`) arrive on
    // the new connection. If the reply already landed we just drop the stale
    // bubble; if the stream closed while idle (no turn in flight) we stop.
    void (async () => {
      // `reconnects` is a per-subscription lifetime cap (not consecutive): a
      // turn that keeps dropping right after its replayed `turn_start` must not
      // reconnect forever, so the counter is intentionally never reset.
      for (let reconnects = 0; !cancelled; ) {
        let turnInFlight = false;
        try {
          for await (const event of subscribeConversationEvents(
            conversationId,
            controller.signal,
          )) {
            if (cancelled) return;
            if (event.event === "turn_start") turnInFlight = true;
            else if (event.event === "turn_done" || event.event === "turn_error")
              turnInFlight = false;
            await handleEvent(event, {
              conversationId,
              qc,
              priorReplyCountRef,
              setIsStreaming,
              setLiveMessage,
              setPendingState,
              setEchoes,
              setError,
              isCancelled: () => cancelled,
            });
          }
        } catch (err) {
          if (cancelled) return;
          if (err instanceof Error && err.name === "AbortError") return;
          // A network/HTTP failure (e.g. the conversation is gone) — surface it
          // and reconcile, but do not reconnect into a failing endpoint.
          const wrapped = err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
          setError(wrapped);
          setIsStreaming(false);
          // Drop the bubble (and the echoes its refetch settled) once the reply
          // is committed; otherwise keep what streamed but stop it "thinking" —
          // the error banner owns the state.
          if (await replyHasLanded()) {
            setLiveMessage(null);
            setEchoes([]);
          } else {
            setLiveMessage((prev) => (prev ? { ...prev, streaming: false } : prev));
          }
          return;
        }

        // Stream closed cleanly (not aborted by us).
        if (cancelled) return;
        if (await replyHasLanded()) {
          // The turn finished and its reply is committed — drop the stale bubble.
          setIsStreaming(false);
          setLiveMessage(null);
          setEchoes([]);
          return;
        }
        if (!turnInFlight || reconnects >= MAX_STREAM_RECONNECTS) {
          // Idle close with no turn to recover, or too many drops — stop, leaving
          // the bubble so the next send's refetch still surfaces any late reply.
          setIsStreaming(false);
          return;
        }
        // A turn was mid-flight when the stream dropped — reconnect to replay it.
        reconnects += 1;
        await sleep(RECONNECT_BACKOFF_MS * reconnects);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [conversationId, qc]);

  const { send, resend } = useChatSend({
    conversationId,
    isStreamingRef,
    setEchoes,
    setError,
    setRefused,
  });

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
    resend,
    isStreaming,
    liveMessage,
    pendingEchoes: echoes,
    error,
    retryable: error !== null && error !== refused,
    clearError,
    interrupt,
    pending,
    setPending,
  };
}
