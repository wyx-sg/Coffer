// frontend/src/lib/hooks/chatTurnEvents.ts
// The SSE event reducer for useChatTurn: folds AgentEvents into a live assistant
// message, tracks the pending queue, and retires the optimistic echoes of prompts
// this client sent (lib/chat/echoes). Extracted so the hook file stays focused.

import type { Dispatch, SetStateAction } from "react";
import { hashKey, type QueryClient } from "@tanstack/react-query";

import type { AgentEvent } from "@/lib/chat/streamClient";
import type { PendingEcho } from "@/lib/chat/echoes";
import type { ContentBlock, Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { messagesKey } from "@/lib/api/queryKeys";

export interface LiveMessage {
  /**
   * The turn's text and tool blocks in the order it emitted them — the same
   * shape the persisted assistant row carries. Consecutive text deltas extend
   * the trailing text block; a tool call or result closes it.
   */
  blocks: ContentBlock[];
  /** Whether the turn is still streaming. */
  streaming: boolean;
}

/** `blocks` with `delta` appended to its trailing text block, or a new one. */
function appendText(blocks: ContentBlock[], delta: string): ContentBlock[] {
  const last = blocks[blocks.length - 1];
  if (last?.type === "text") {
    return [...blocks.slice(0, -1), { ...last, text: (last.text ?? "") + delta }];
  }
  return [...blocks, { type: "text", text: delta }];
}

/** Fold one content block into the live bubble, starting one if none is shown. */
function withBlocks(
  prev: LiveMessage | null,
  next: (blocks: ContentBlock[]) => ContentBlock[],
): LiveMessage {
  return { blocks: next(prev?.blocks ?? []), streaming: true };
}

/**
 * Call `onMessages` with the conversation's message rows whenever their query
 * cache entry is (re)filled — a refetch or a setQueryData. This listens on the
 * cache, not through a query observer, so it never triggers a fetch of its own.
 */
export function subscribeMessagesCache(
  qc: QueryClient,
  conversationId: string,
  onMessages: (messages: Message[]) => void,
): () => void {
  const hash = hashKey(messagesKey(conversationId));
  return qc.getQueryCache().subscribe((event) => {
    if (event.type !== "updated" || event.action.type !== "success") return;
    if (event.query.queryHash !== hash) return;
    const rows = event.query.state.data as Message[] | undefined;
    if (rows) onMessages(rows);
  });
}

// ---------------------------------------------------------------------------
// Event reducer
// ---------------------------------------------------------------------------

/** Count of complete assistant replies — used to detect a NEW reply landing. */
function completeReplyCount(messages: Message[]): number {
  return messages.filter((m) => m.role === "assistant" && m.status === "complete").length;
}

export interface HandlerCtx {
  conversationId: string;
  qc: QueryClient;
  /**
   * Complete-reply count captured at turn_start, so turn_done can tell when a
   * NEW reply has landed (works for text and tool-only turns alike, and never
   * false-matches a prior turn's reply).
   */
  priorReplyCountRef: { current: number };
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setLiveMessage: Dispatch<SetStateAction<LiveMessage | null>>;
  setPendingState: Dispatch<SetStateAction<string[]>>;
  setEchoes: Dispatch<SetStateAction<PendingEcho[]>>;
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
    setEchoes,
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
      // so this client may hold no echo for it. Begin a fresh live bubble and
      // invalidate messages so the committed user message appears (which is
      // also what retires this client's own echo, via the cache subscription).
      setLiveMessage({ blocks: [], streaming: true });
      await qc.invalidateQueries({ queryKey: messagesKey(conversationId) });
      break;

    case "text_delta":
      setLiveMessage((prev) => withBlocks(prev, (blocks) => appendText(blocks, event.data.text)));
      break;

    case "tool_call": {
      const block: ContentBlock = {
        type: "tool_use",
        tool_use_id: event.data.tool_use_id,
        tool_name: event.data.tool_name,
        tool_input: event.data.tool_input,
      };
      setLiveMessage((prev) => withBlocks(prev, (blocks) => [...blocks, block]));
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
      setLiveMessage((prev) => withBlocks(prev, (blocks) => [...blocks, resultBlock]));
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
      // The turn is settled: its user row was persisted before it ran and that
      // refetch has now been seen, so any echo still standing (e.g. one outside
      // the match window) is a ghost — drop them all.
      setEchoes([]);
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
      setEchoes([]);
      setLiveMessage(null);
      break;
    }

    case "queue_changed":
      setPendingState(event.data.pending);
      break;
  }
}
