// frontend/src/lib/hooks/chatTurnEvents.test.ts
// The optimistic-echo reducer: an echo is matched to its persisted row without a
// wire id, by text + time window + ordering, and never left as a ghost.
import { describe, expect, test, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import type { Message } from "@/lib/api/chat";
import {
  ECHO_MATCH_WINDOW_MS,
  createEcho,
  handleEvent,
  reconcileEchoes,
  subscribeMessagesCache,
  type HandlerCtx,
  type LiveMessage,
  type PendingEcho,
} from "./chatTurnEvents";
import { messagesKey } from "@/lib/api/queryKeys";

const T0 = Date.parse("2026-01-01T12:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();

function userRow(id: string, seq: number, text: string, createdAt: number): Message {
  return {
    id,
    conversation_id: "conv-1",
    seq,
    role: "user",
    content: [{ type: "text", text }],
    status: "complete",
    created_at: iso(createdAt),
  };
}

function assistantRow(id: string, seq: number, text: string): Message {
  return {
    id,
    conversation_id: "conv-1",
    seq,
    role: "assistant",
    content: [{ type: "text", text }],
    status: "complete",
    created_at: iso(T0),
  };
}

describe("createEcho", () => {
  test("remembers the highest seq the client had fetched, and -1 for an empty thread", () => {
    expect(createEcho("hi", [], T0).afterSeq).toBe(-1);
    const echo = createEcho("hi", [userRow("u1", 1, "hi", T0), assistantRow("a1", 2, "yo")], T0);
    expect(echo).toMatchObject({ text: "hi", sentAt: T0, afterSeq: 2 });
  });

  test("each echo gets a distinct render key", () => {
    expect(createEcho("hi", [], T0).id).not.toBe(createEcho("hi", [], T0).id);
  });
});

describe("reconcileEchoes", () => {
  test("identical consecutive prompts both keep their echo and both clear against two distinct rows", () => {
    // (a) The thread already holds "hi" → "yo"; the user sends "again" twice
    // in a row. Text alone can't tell the two apart — each must be retired by
    // its OWN row, not both by the first.
    const known = [userRow("u1", 1, "hi", T0 - 10_000), assistantRow("a1", 2, "yo")];
    const first = createEcho("again", known, T0);
    const second = createEcho("again", known, T0 + 100);
    let echoes = [first, second];

    // Nothing persisted yet → both echoes stand.
    expect(reconcileEchoes(echoes, known)).toBe(echoes);

    // The first row lands: only the first echo retires.
    const withOne = [...known, userRow("u3", 3, "again", T0 + 500)];
    echoes = reconcileEchoes(echoes, withOne);
    expect(echoes.map((e) => e.id)).toEqual([second.id]);

    // The survivor must not re-match row u3 on the next pass: it carries the
    // claimed seq forward as its floor.
    expect(reconcileEchoes(echoes, withOne)).toBe(echoes);

    // The second row lands: the second echo retires against it.
    const withBoth = [...withOne, userRow("u4", 4, "again", T0 + 900)];
    expect(reconcileEchoes(echoes, withBoth)).toEqual([]);
  });

  test("both rows arriving in one refetch retire both echoes", () => {
    const first = createEcho("again", [], T0);
    const second = createEcho("again", [], T0 + 100);
    const rows = [userRow("u1", 1, "again", T0 + 300), userRow("u2", 2, "again", T0 + 600)];
    expect(reconcileEchoes([first, second], rows)).toEqual([]);
  });

  test("an echo never matches an older identical prompt already in the thread", () => {
    // (b) "again" was sent a minute ago and sits at seq 1. The new echo was
    // created knowing seq 2 exists, so the old row (seq 1) can't claim it —
    // even though its text is identical.
    const known = [userRow("u1", 1, "again", T0 - 30_000), assistantRow("a1", 2, "ok")];
    const echo = createEcho("again", known, T0);
    expect(reconcileEchoes([echo], known)).toEqual([echo]);
  });

  test("an identical row from before the echo was created can't claim it even with a newer seq", () => {
    // The seq rule handles what the client had fetched; the time window handles
    // a row the client had NOT fetched yet but which predates the send (e.g. the
    // same text sent from an IM channel well before).
    const echo = createEcho("again", [], T0);
    const stale = userRow("u9", 9, "again", T0 - ECHO_MATCH_WINDOW_MS);
    expect(reconcileEchoes([echo], [stale])).toEqual([echo]);
  });

  test("a row created after the match window does not claim the echo", () => {
    const echo = createEcho("again", [], T0);
    const late = userRow("u2", 2, "again", T0 + ECHO_MATCH_WINDOW_MS + 1);
    expect(reconcileEchoes([echo], [late])).toEqual([echo]);
    const inTime = userRow("u2", 2, "again", T0 + ECHO_MATCH_WINDOW_MS);
    expect(reconcileEchoes([echo], [inTime])).toEqual([]);
  });

  test("assistant rows and rows with different text never claim an echo", () => {
    const echo = createEcho("question", [], T0);
    const rows = [assistantRow("a1", 1, "question"), userRow("u2", 2, "other", T0 + 10)];
    expect(reconcileEchoes([echo], rows)).toEqual([echo]);
  });

  test("a row without a parseable created_at is matched by text + seq alone", () => {
    const echo = createEcho("q", [], T0);
    const row = { ...userRow("u1", 1, "q", T0), created_at: "" };
    expect(reconcileEchoes([echo], [row])).toEqual([]);
  });
});

describe("subscribeMessagesCache", () => {
  test("fires with the rows on every fill of this conversation's messages cache only", () => {
    const qc = new QueryClient();
    const seen: Message[][] = [];
    const unsubscribe = subscribeMessagesCache(qc, "conv-1", (rows) => seen.push(rows));

    qc.setQueryData(messagesKey("conv-2"), [userRow("x", 1, "other conv", T0)]);
    qc.setQueryData(messagesKey("conv-1"), [userRow("u1", 1, "q", T0)]);
    qc.setQueryData(messagesKey("conv-1"), [userRow("u1", 1, "q", T0), assistantRow("a1", 2, "a")]);
    expect(seen.map((rows) => rows.length)).toEqual([1, 2]);

    unsubscribe();
    qc.setQueryData(messagesKey("conv-1"), []);
    expect(seen).toHaveLength(2);
  });
});

describe("handleEvent settles echoes", () => {
  function makeCtx(qc: QueryClient) {
    const echoes: PendingEcho[][] = [];
    const ctx: HandlerCtx = {
      conversationId: "conv-1",
      qc,
      priorReplyCountRef: { current: 0 },
      setIsStreaming: vi.fn(),
      setLiveMessage: vi.fn(),
      setPendingState: vi.fn(),
      setEchoes: vi.fn((next) => {
        echoes.push(typeof next === "function" ? next([]) : next);
      }),
      setError: vi.fn(),
      isCancelled: () => false,
    };
    return { ctx, echoes };
  }

  test("turn_done drops every echo, even one whose match window has passed (no ghost bubble)", async () => {
    // (c) The row was persisted but arrived with a created_at outside the
    // window (a slow agent spawn, a clock hiccup) — matching never retires the
    // echo, so the turn settling must.
    const qc = new QueryClient();
    const { ctx, echoes } = makeCtx(qc);
    await handleEvent({ event: "turn_done", data: { stop_reason: "end_turn" } }, ctx);
    expect(echoes).toEqual([[]]);
  });

  test("an interrupted turn_done also drops the echoes", async () => {
    // (d) Stop mid-turn: the turn settles with an interrupted stop reason.
    const qc = new QueryClient();
    const { ctx, echoes } = makeCtx(qc);
    await handleEvent({ event: "turn_done", data: { stop_reason: "interrupted" } }, ctx);
    expect(echoes).toEqual([[]]);
  });

  test("turn_error drops the echoes after the refetch", async () => {
    // (d) A failed turn: the persisted user row + failed reply replace the echo.
    const qc = new QueryClient();
    const { ctx, echoes } = makeCtx(qc);
    await handleEvent({ event: "turn_error", data: { code: "MODEL_ERROR", message: "x" } }, ctx);
    expect(echoes).toEqual([[]]);
    expect(ctx.setLiveMessage).toHaveBeenCalledWith(null);
  });

  test("turn_start leaves the echoes alone (the refetch it triggers retires them)", async () => {
    const qc = new QueryClient();
    const { ctx } = makeCtx(qc);
    await handleEvent({ event: "turn_start", data: {} }, ctx);
    expect(ctx.setEchoes).not.toHaveBeenCalled();
  });

  test("a settle after the conversation was switched away does not touch state", async () => {
    const qc = new QueryClient();
    const { ctx } = makeCtx(qc);
    ctx.isCancelled = () => true;
    await handleEvent({ event: "turn_done", data: { stop_reason: "end_turn" } }, ctx);
    expect(ctx.setEchoes).not.toHaveBeenCalled();
  });
});

describe("handleEvent folds a turn into the live bubble in emission order", () => {
  test("text before a tool call stays before it, and text after it is a new block", async () => {
    const qc = new QueryClient();
    let live: LiveMessage | null = { blocks: [], streaming: true };
    const ctx: HandlerCtx = {
      conversationId: "conv-1",
      qc,
      priorReplyCountRef: { current: 0 },
      setIsStreaming: vi.fn(),
      setLiveMessage: vi.fn((next) => {
        live = typeof next === "function" ? next(live) : next;
      }),
      setPendingState: vi.fn(),
      setEchoes: vi.fn(),
      setError: vi.fn(),
      isCancelled: () => false,
    };

    await handleEvent({ event: "text_delta", data: { text: "Let me " } }, ctx);
    await handleEvent({ event: "text_delta", data: { text: "look." } }, ctx);
    await handleEvent(
      {
        event: "tool_call",
        data: { tool_use_id: "tu-1", tool_name: "read_file", tool_input: { path: "a" } },
      },
      ctx,
    );
    await handleEvent(
      {
        event: "tool_result",
        data: { tool_use_id: "tu-1", tool_name: "read_file", output: { ok: 1 }, error: null },
      },
      ctx,
    );
    await handleEvent({ event: "text_delta", data: { text: "It says hi." } }, ctx);

    expect(live!.blocks.map((b) => [b.type, b.text ?? b.tool_use_id])).toEqual([
      ["text", "Let me look."],
      ["tool_use", "tu-1"],
      ["tool_result", "tu-1"],
      ["text", "It says hi."],
    ]);
  });
});
