// frontend/src/lib/hooks/useChatTurn.ts
// Holds a persistent GET /events subscription for the active conversation and
// accumulates SSE agent events into a live assistant message for the Chat page
// to render.
//
// API:
//   const { send, isStreaming, liveMessage, error, clearError,
//           interrupt, pending, setPending } = useChatTurn(convId);
//
// The subscription is opened on the active conversation and stays open across
// turns (it replays the in-flight turn then streams live). `send` is
// fire-and-return: it POSTs the message and returns immediately — the turn's
// events arrive over the subscription, not the POST. `liveMessage` is non-null
// while a turn is in flight (it carries the user's just-sent prompt as an
// optimistic echo plus the streaming reply) and is cleared once the persisted
// reply lands (via messages query invalidation on turn_done / turn_error).

import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { subscribeConversationEvents, type AgentEvent } from "@/lib/chat/streamClient";
import { chatApi, type ContentBlock, type Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { CONVERSATIONS_KEY, messagesKey } from "./useConversations";

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

export interface LiveMessage {
  /**
   * The prompt that started this turn — echoed in the thread immediately so
   * the user's message is visible while the reply streams (the persisted row
   * takes over once the next messages fetch lands).
   */
  userText?: string;
  /** Partial accumulated text from text_delta events. */
  text: string;
  /** Tool call/result blocks accumulated during the turn. */
  toolBlocks: ContentBlock[];
  /** Whether the turn is still streaming. */
  streaming: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

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

  // The streamed assistant text of the current turn — used to confirm the
  // persisted reply has landed before dropping the live bubble (avoids a
  // flicker where the bubble blanks into a gap before the keyed persisted row
  // renders). Kept in a ref so the subscription effect doesn't re-run per token.
  const assistantTextRef = useRef("");

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
    assistantTextRef.current = "";

    void (async () => {
      try {
        for await (const event of subscribeConversationEvents(conversationId, controller.signal)) {
          if (cancelled) return;
          await handleEvent(event, {
            conversationId,
            qc,
            assistantTextRef,
            setIsStreaming,
            setLiveMessage,
            setPendingState,
            setError,
            isCancelled: () => cancelled,
          });
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.name === "AbortError") return;
        const wrapped = err instanceof Error ? err : new ApiError("INTERNAL_ERROR", String(err));
        setError(wrapped);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [conversationId, qc]);

  const send = useCallback(
    async (text: string) => {
      // Fire-and-return: NEVER blocks on an in-flight turn. A second message
      // sent mid-turn is queued server-side and surfaced via queue_changed.
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
        // The first turn renames the conversation server-side (auto-title);
        // refresh the list whether the send succeeded or failed.
        void qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
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

// ---------------------------------------------------------------------------
// Reply alignment
// ---------------------------------------------------------------------------

/**
 * Has the refetched history caught up with the turn that just streamed — i.e.
 * does it carry this turn's assistant reply? Align by the streamed text (a
 * complete assistant message whose text matches what streamed); for a reply
 * with no text (a tool-only turn) fall back to existence of any complete
 * assistant message. Used to gate clearing the live bubble so it never blanks
 * into a gap before the persisted bubble renders.
 */
function assistantReplyLanded(messages: Message[], streamedText: string): boolean {
  const replies = messages.filter((m) => m.role === "assistant" && m.status === "complete");
  const wanted = streamedText.trim();
  if (!wanted) return replies.length > 0;
  return replies.some((m) => {
    const text = m.content
      .filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("");
    return text.trim() === wanted || text.includes(wanted);
  });
}

// ---------------------------------------------------------------------------
// Event handler
// ---------------------------------------------------------------------------

interface HandlerCtx {
  conversationId: string;
  qc: ReturnType<typeof useQueryClient>;
  assistantTextRef: { current: string };
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setLiveMessage: Dispatch<SetStateAction<LiveMessage | null>>;
  setPendingState: Dispatch<SetStateAction<string[]>>;
  setError: Dispatch<SetStateAction<Error | null>>;
  isCancelled: () => boolean;
}

async function handleEvent(event: AgentEvent, ctx: HandlerCtx): Promise<void> {
  const {
    conversationId,
    qc,
    assistantTextRef,
    setIsStreaming,
    setLiveMessage,
    setPendingState,
    setError,
    isCancelled,
  } = ctx;

  switch (event.event) {
    case "turn_start":
      assistantTextRef.current = "";
      setIsStreaming(true);
      // A turn may have been started from another surface (e.g. an IM channel),
      // so this client holds no optimistic echo. Begin a fresh live bubble and
      // invalidate messages so the committed user message appears.
      setLiveMessage((prev) =>
        prev
          ? { ...prev, text: "", toolBlocks: [], streaming: true }
          : { text: "", toolBlocks: [], streaming: true },
      );
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      break;

    case "text_delta":
      assistantTextRef.current += event.data.text;
      setLiveMessage((prev) =>
        prev
          ? { ...prev, text: prev.text + event.data.text, streaming: true }
          : { text: event.data.text, toolBlocks: [], streaming: true },
      );
      break;

    case "tool_call": {
      const block: ContentBlock = {
        type: "tool_use",
        tool_use_id: event.data.tool_use_id,
        tool_name: event.data.tool_name,
        tool_input: event.data.tool_input,
      };
      setLiveMessage((prev) =>
        prev
          ? { ...prev, toolBlocks: [...prev.toolBlocks, block], streaming: true }
          : { text: "", toolBlocks: [block], streaming: true },
      );
      break;
    }

    case "tool_result": {
      const resultBlock: ContentBlock = {
        type: "tool_result",
        tool_use_id: event.data.tool_use_id,
        tool_name: event.data.tool_name,
        output: event.data.output ?? null,
        error: event.data.error ?? null,
      };
      setLiveMessage((prev) =>
        prev
          ? { ...prev, toolBlocks: [...prev.toolBlocks, resultBlock], streaming: true }
          : { text: "", toolBlocks: [resultBlock], streaming: true },
      );
      break;
    }

    case "turn_done": {
      setIsStreaming(false);
      setLiveMessage((prev) => (prev ? { ...prev, streaming: false } : null));
      // Refetch the persisted messages, then drop the live bubble ONLY once
      // that refetch actually carries this turn's assistant reply. Clearing
      // before it lands removes the live bubble into a gap (the keyed persisted
      // bubble hasn't rendered yet), so the just-streamed answer flickers out
      // and back in. Aligning on the reply closes the gap.
      const streamedText = assistantTextRef.current;
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      if (isCancelled()) return;
      const refetched = qc.getQueryData<Message[]>(messagesKey(conversationId)) ?? [];
      if (assistantReplyLanded(refetched, streamedText)) {
        setLiveMessage(null);
      }
      break;
    }

    case "turn_error": {
      setIsStreaming(false);
      setError(new ApiError(event.data.code, event.data.message));
      // The stream did not finish the turn — refetch so the persisted user
      // message and the failed turn replace the optimistic echo / live bubble.
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      if (isCancelled()) return;
      setLiveMessage(null);
      break;
    }

    case "queue_changed":
      setPendingState(event.data.pending);
      break;
  }
}
