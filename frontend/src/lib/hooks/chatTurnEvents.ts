// frontend/src/lib/hooks/chatTurnEvents.ts
// The SSE event reducer for useChatTurn: folds AgentEvents into a live assistant
// message, tracks the pending queue, and owns the optimistic echo of prompts this
// client sent. Extracted so the hook file stays focused.

import type { Dispatch, SetStateAction } from "react";
import { hashKey, type QueryClient } from "@tanstack/react-query";

import type { AgentEvent } from "@/lib/chat/streamClient";
import type { ContentBlock, Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import { messagesKey } from "@/lib/api/queryKeys";

export interface LiveMessage {
  /** Partial accumulated text from text_delta events. */
  text: string;
  /** Tool call/result blocks accumulated during the turn. */
  toolBlocks: ContentBlock[];
  /** Whether the turn is still streaming. */
  streaming: boolean;
}

// ---------------------------------------------------------------------------
// Optimistic echo of a just-sent prompt
// ---------------------------------------------------------------------------

/**
 * A prompt this client sent whose persisted user row has not been fetched yet.
 * The thread renders it as a user bubble so the message is visible before the
 * next messages refetch lands.
 *
 * The wire carries no client-generated id (POST .../messages takes only `text`
 * and `turn_start` carries nothing), so an echo cannot be matched to its row by
 * id. It is matched by text AND time AND ordering instead — see reconcileEchoes.
 */
export interface PendingEcho {
  /** Stable render key. */
  id: string;
  text: string;
  /** Client clock (ms since epoch) when the send was issued. */
  sentAt: number;
  /**
   * Highest `seq` this client had already fetched when the send was issued.
   * Only a row with a greater seq can claim the echo, so an identical prompt
   * already in the thread can never satisfy the new one.
   */
  afterSeq: number;
}

/**
 * A persisted user row claims an echo only when its `created_at` falls within
 * this long AFTER the echo's `sentAt`. Generous: the daemon persists the row
 * when the turn starts, which may wait on agent spawn. An echo the window has
 * passed is still dropped once its turn settles (turn_done / turn_error), so a
 * slow start never leaves a ghost bubble.
 */
export const ECHO_MATCH_WINDOW_MS = 60_000;
/**
 * How far BEFORE `sentAt` a row's `created_at` may land and still match. The
 * daemon is local, so server/client drift is small; this only absorbs it.
 */
const ECHO_CLOCK_SKEW_MS = 5_000;

let echoSerial = 0;

/** Build the echo for a send issued now, given the rows the client has fetched. */
export function createEcho(text: string, known: Message[], now: number = Date.now()): PendingEcho {
  const afterSeq = known.reduce((max, m) => Math.max(max, m.seq), -1);
  echoSerial += 1;
  return { id: `echo-${echoSerial}`, text, sentAt: now, afterSeq };
}

function createdAtMs(row: Message): number | null {
  const t = Date.parse(row.created_at);
  return Number.isNaN(t) ? null : t;
}

function rowClaimsEcho(row: Message, echo: PendingEcho): boolean {
  if (row.role !== "user" || row.seq <= echo.afterSeq) return false;
  if (!row.content.some((b) => b.type === "text" && b.text === echo.text)) return false;
  const created = createdAtMs(row);
  // A row with no parseable timestamp cannot be placed in time; the seq rule
  // above still guards against an older identical prompt.
  if (created === null) return true;
  return (
    created >= echo.sentAt - ECHO_CLOCK_SKEW_MS && created <= echo.sentAt + ECHO_MATCH_WINDOW_MS
  );
}

/**
 * Drop every echo whose persisted user row is now in `messages`.
 *
 * Echoes are walked in send order and each row claims at most one echo, so two
 * identical consecutive prompts resolve against two distinct rows. Sends are
 * ordered, so once a row with seq S claims an echo, every later echo can only be
 * claimed by a row after S — the survivors carry that floor forward in
 * `afterSeq`, which keeps a later reconcile from re-matching the same row.
 * Returns the same array when nothing changed so a setState is a no-op.
 */
export function reconcileEchoes(echoes: PendingEcho[], messages: Message[]): PendingEcho[] {
  if (echoes.length === 0) return echoes;
  const claimed = new Set<string>();
  let floorSeq = -1;
  const remaining: PendingEcho[] = [];
  for (const echo of echoes) {
    const row = messages.find(
      (m) => !claimed.has(m.id) && m.seq > floorSeq && rowClaimsEcho(m, echo),
    );
    if (row) {
      claimed.add(row.id);
      floorSeq = row.seq;
    } else {
      remaining.push(echo.afterSeq < floorSeq ? { ...echo, afterSeq: floorSeq } : echo);
    }
  }
  return remaining.length === echoes.length ? echoes : remaining;
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
      setLiveMessage({ text: "", toolBlocks: [], streaming: true });
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
