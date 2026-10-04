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
import { type PendingEcho, reconcileEchoes } from "@/lib/chat/echoes";
import { type LiveMessage, handleEvent, subscribeMessagesCache } from "./chatTurnEvents";
import { useChatSend } from "./useChatSend";
import type { UseChatTurnResult } from "./useChatTurnResult";

export type { LiveMessage } from "./chatTurnEvents";
export type { PendingEcho } from "@/lib/chat/echoes";
export type { UseChatTurnResult } from "./useChatTurnResult";

// A dropped stream is recovered by re-subscribing (GET /events replays the
// in-flight turn), bounded so a hard failure can't hammer the endpoint: a few
// consecutive attempts that deliver nothing, and a generous lifetime cap per
// subscription (a long-lived page legitimately outlives some drops).
const MAX_CONSECUTIVE_FAILURES = 5;
const MAX_STREAM_RECONNECTS = 100;
const RECONNECT_BACKOFF_MS = 300;
const MAX_BACKOFF_MS = 5000;

export function useChatTurn(conversationId: string): UseChatTurnResult {
  const qc = useQueryClient();
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveMessage, setLiveMessage] = useState<LiveMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPendingState] = useState<string[]>([]);
  const [echoes, setEchoes] = useState<PendingEcho[]>([]);
  // The last error that was a refused POST rather than a failed turn.
  const [refused, setRefused] = useState<Error | null>(null);
  const [streamLost, setStreamLost] = useState(false);
  // A turn_error arrived while no turn was running: the shape of a failed queued
  // start. Only with a non-empty queue is the queue "held" (derived below), so
  // the order of this event and the queue snapshot on the wire does not matter.
  const [errorOutsideTurn, setErrorOutsideTurn] = useState(false);
  // Bumped by `reload` to open a fresh subscription on the same conversation.
  const [subscription, setSubscription] = useState(0);

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
    setStreamLost(false);
    setErrorOutsideTurn(false);
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
    // and the server holds it open when idle), so ANY end of it that we did not
    // cause — a clean close, a network drop mid-read, a failed re-connect — is
    // recovered by RE-SUBSCRIBING (spec chat "Recover a dropped event stream with
    // bounded retries"): GET /events replays the in-flight turn on reattach, so
    // events missed mid-turn (including `turn_done`) arrive on the new
    // connection, and an idle subscription simply holds open again. Retries back
    // off and are bounded; a segment that delivers an event proves the endpoint
    // is alive and resets the consecutive count, while the lifetime cap still
    // stops a turn that keeps dropping right after its replayed `turn_start`.
    // An HTTP error response (e.g. 404, the conversation is gone) is not
    // retried: hammering a refusing endpoint helps nobody.
    void (async () => {
      let failures = 0; // consecutive segments that ended without delivering an event
      let reconnects = 0; // lifetime
      let turnInFlight = false;
      while (!cancelled) {
        let delivered = false;
        try {
          for await (const event of subscribeConversationEvents(
            conversationId,
            controller.signal,
          )) {
            if (cancelled) return;
            delivered = true;
            if (event.event === "turn_start") {
              turnInFlight = true;
              setErrorOutsideTurn(false);
            } else if (event.event === "turn_done") {
              turnInFlight = false;
            } else if (event.event === "turn_error") {
              setErrorOutsideTurn(!turnInFlight);
              turnInFlight = false;
            }
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
          if (err instanceof ApiError) {
            // The endpoint answered with a refusal — surface it and reconcile,
            // but do not reconnect into it.
            setError(err);
            setIsStreaming(false);
            // Drop the bubble (and the echoes its refetch settled) once the
            // reply is committed; otherwise keep what streamed but stop it
            // "thinking" — the error banner owns the state.
            if (await replyHasLanded()) {
              setLiveMessage(null);
              setEchoes([]);
            } else {
              setLiveMessage((prev) => (prev ? { ...prev, streaming: false } : prev));
            }
            return;
          }
          // Anything else is a network drop (fetch or read threw): recover below.
        }
        if (cancelled) return;

        if (turnInFlight && (await replyHasLanded())) {
          // The turn finished and its reply is committed — drop the stale bubble.
          turnInFlight = false;
          setIsStreaming(false);
          setLiveMessage(null);
          setEchoes([]);
        }

        failures = delivered ? 0 : failures + 1;
        if (failures > MAX_CONSECUTIVE_FAILURES || reconnects >= MAX_STREAM_RECONNECTS) {
          // Out of attempts. Say so out loud — the turn may still be running —
          // and leave the bubble so a later refetch still surfaces a late reply.
          setIsStreaming(false);
          setStreamLost(true);
          return;
        }
        reconnects += 1;
        await sleep(Math.min(RECONNECT_BACKOFF_MS * Math.max(failures, 1), MAX_BACKOFF_MS));
        // The turn may have finished while we were away: its replay is then
        // empty, and a subscription that holds open would never end the bubble.
        if (turnInFlight && !cancelled && (await replyHasLanded())) {
          turnInFlight = false;
          setIsStreaming(false);
          setLiveMessage(null);
          setEchoes([]);
        }
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [conversationId, qc, subscription]);

  const reload = useCallback(() => {
    if (!conversationId) return;
    void qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
    setSubscription((n) => n + 1);
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

  const clearError = useCallback(() => {
    setError(null);
    setErrorOutsideTurn(false);
  }, []);

  const queueHeld = error !== null && errorOutsideTurn && pending.length > 0;

  const resumeQueue = useCallback(async () => {
    setError(null);
    setErrorOutsideTurn(false);
    await setPending(pending);
  }, [pending, setPending]);

  return {
    send,
    resend,
    isStreaming,
    liveMessage,
    pendingEchoes: echoes,
    error,
    retryable: error !== null && error !== refused && !queueHeld,
    clearError,
    interrupt,
    queueHeld,
    resumeQueue,
    pending,
    setPending,
    streamLost,
    reload,
  };
}
