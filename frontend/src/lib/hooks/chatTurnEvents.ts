// frontend/src/lib/hooks/chatTurnEvents.ts
// The SSE event reducer for useChatTurn: folds AgentEvents into a live assistant
// message and tracks the pending queue. Extracted so the hook file stays focused.

import type { Dispatch, SetStateAction } from "react";
import type { useQueryClient } from "@tanstack/react-query";

import type { AgentEvent } from "@/lib/chat/streamClient";
import type { ContentBlock, Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { messagesKey } from "./useConversations";

export interface LiveMessage {
  /**
   * The prompt that started this turn — echoed in the thread immediately so the
   * user's message is visible while the reply streams (the persisted row takes
   * over once the next messages fetch lands).
   */
  userText?: string;
  /** Partial accumulated text from text_delta events. */
  text: string;
  /** Tool call/result blocks accumulated during the turn. */
  toolBlocks: ContentBlock[];
  /** Whether the turn is still streaming. */
  streaming: boolean;
}

/** Count of complete assistant replies — used to detect a NEW reply landing. */
function completeReplyCount(messages: Message[]): number {
  return messages.filter((m) => m.role === "assistant" && m.status === "complete").length;
}

export interface HandlerCtx {
  conversationId: string;
  qc: ReturnType<typeof useQueryClient>;
  /**
   * Complete-reply count captured at turn_start, so turn_done can tell when a
   * NEW reply has landed (works for text and tool-only turns alike, and never
   * false-matches a prior turn's reply).
   */
  priorReplyCountRef: { current: number };
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setLiveMessage: Dispatch<SetStateAction<LiveMessage | null>>;
  setPendingState: Dispatch<SetStateAction<string[]>>;
  setError: Dispatch<SetStateAction<Error | null>>;
  isCancelled: () => boolean;
}

export async function handleEvent(event: AgentEvent, ctx: HandlerCtx): Promise<void> {
  const {
    conversationId,
    qc,
    priorReplyCountRef,
    setIsStreaming,
    setLiveMessage,
    setPendingState,
    setError,
    isCancelled,
  } = ctx;

  switch (event.event) {
    case "turn_start":
      // Record how many complete replies exist BEFORE this turn so turn_done can
      // detect the new one landing without fragile text matching.
      priorReplyCountRef.current = completeReplyCount(
        qc.getQueryData<Message[]>(messagesKey(conversationId)) ?? [],
      );
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
      // Refetch the persisted messages, then drop the live bubble ONLY once that
      // refetch carries a NEW complete reply (count increased). Clearing before
      // it lands removes the live bubble into a gap (the keyed persisted bubble
      // hasn't rendered yet), so the just-streamed answer flickers out and back.
      const prior = priorReplyCountRef.current;
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      if (isCancelled()) return;
      const refetched = qc.getQueryData<Message[]>(messagesKey(conversationId)) ?? [];
      if (completeReplyCount(refetched) > prior) {
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
