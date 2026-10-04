// frontend/src/lib/hooks/useChatSend.ts
// The two POSTs that may start a chat turn — a send and a Retry's resend — for
// useChatTurn, which owns the state they write. Both are fire-and-return: the
// turn's events arrive over the conversation's subscription, not the POST.

import { useCallback, type Dispatch, type RefObject, type SetStateAction } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { chatApi, type Message, type SendMessageAck } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { conversationHeadsKey, conversationKey, messagesKey } from "@/lib/api/queryKeys";
import { type EchoAttachment, type PendingEcho, createEcho } from "@/lib/chat/echoes";

interface Options {
  conversationId: string;
  /** Whether a turn is in flight: a send now is queued and gets no echo. */
  isStreamingRef: RefObject<boolean>;
  setEchoes: Dispatch<SetStateAction<PendingEcho[]>>;
  setError: Dispatch<SetStateAction<Error | null>>;
  /** Records the error of a refused POST, as opposed to a failed turn. */
  setRefused: Dispatch<SetStateAction<Error | null>>;
}

export function useChatSend({
  conversationId,
  isStreamingRef,
  setEchoes,
  setError,
  setRefused,
}: Options) {
  const qc = useQueryClient();

  // One POST that may start a turn. Resolves whether the daemon accepted it; a
  // refusal is surfaced as `error` and remembered as a refusal — its message
  // never ran, so the banner offers no Retry of it.
  const post = useCallback(
    async (request: () => Promise<SendMessageAck>, echo: PendingEcho | null) => {
      setError(null);
      if (echo) setEchoes((prev) => [...prev, echo]);
      const dropEcho = () => {
        if (echo) setEchoes((prev) => prev.filter((e) => e.id !== echo.id));
      };
      try {
        // Queued behind a turn this client did not know about: no row exists
        // yet and the queue chip owns the message until its turn starts.
        const ack = await request();
        if (ack.queued) dropEcho();
        // The channel could not take the reply yet: refetch the conversation so
        // its mirror lists it as undelivered (spec chat "Show where a reply will
        // also be sent"). A "sent" reply changes nothing the page shows.
        if (ack.mirror === "pending") {
          void qc.invalidateQueries({ queryKey: conversationKey(conversationId) });
        }
        return true;
      } catch (err) {
        const wrapped = err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
        setRefused(wrapped);
        dropEcho();
        return false;
      } finally {
        // Refresh the conversation list's head (first turn auto-titles it) AND the
        // messages. The messages refetch is the safety net for the draft→first-
        // send race: if the turn finished before the subscription attached (the
        // bus ring buffer is already cleared), turn_start/turn_done never fire on
        // this client, so nothing else would load the committed user message and
        // reply — leaving the optimistic echo stranded.
        void qc.invalidateQueries({ queryKey: conversationHeadsKey });
        void qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      }
    },
    [conversationId, qc, setEchoes, setError, setRefused],
  );

  // NEVER blocks on an in-flight turn: a message sent mid-turn is queued
  // server-side and shown by the queue chip, so it gets no optimistic echo.
  // Otherwise the echo remembers what this client had already fetched so its
  // own row — and never an older identical prompt — retires it, and keeps the
  // files' upload ids so a Retry before that row lands re-sends them.
  const send = useCallback(
    (text: string, attachments: EchoAttachment[] = []) => {
      const echo = isStreamingRef.current
        ? null
        : createEcho(
            text,
            qc.getQueryData<Message[]>(messagesKey(conversationId)) ?? [],
            Date.now(),
            attachments.map(({ id, filename, mime }) => ({ id, filename, mime })),
          );
      const ids = attachments.map((a) => a.id);
      return post(() => chatApi.sendMessage(conversationId, text, ids), echo);
    },
    [conversationId, isStreamingRef, post, qc],
  );

  // Retry of a persisted message: the daemon rebuilds it from its row, so the
  // attachments travel too; a file swept since refuses it (ATTACHMENT_EXPIRED).
  const resend = useCallback(
    (messageId: string) => post(() => chatApi.resendMessage(conversationId, messageId), null),
    [conversationId, post],
  );

  return { send, resend };
}
