// frontend/src/lib/chat/streamClient.test.ts
// Tests for SSE streaming client.
// Uses a fake ReadableStream to simulate the server-sent event stream.

import { beforeEach, describe, expect, test, vi } from "vitest";
import { streamChatTurn } from "./streamClient";
import { ApiError } from "../api/errors";

// Mock auth helpers so they return deterministic values.
vi.mock("../auth", () => ({
  getCofferBaseUrl: () => "http://127.0.0.1:8000/api/v1",
  getCofferToken: () => "test-token",
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a ReadableStream that emits the given SSE text chunks. */
function makeStream(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index++]));
      } else {
        controller.close();
      }
    },
  });
}

/** Format a single SSE frame string. */
function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("streamChatTurn", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  test("yields turn_start, text_delta, turn_done from a simple stream", async () => {
    const body = makeStream(
      sseFrame("turn_start", { conversation_id: "c1", message_id: "m1" }),
      sseFrame("text_delta", { text: "Hello" }),
      sseFrame("text_delta", { text: " world" }),
      sseFrame("turn_done", { message_id: "m1", prompt_tokens: 10, completion_tokens: 5 }),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body,
      }),
    );

    const events = [];
    for await (const event of streamChatTurn("c1", "hi")) {
      events.push(event);
    }

    expect(events).toHaveLength(4);
    expect(events[0].event).toBe("turn_start");
    expect(events[1].event).toBe("text_delta");
    expect((events[1] as { event: string; data: { text: string } }).data.text).toBe("Hello");
    expect(events[2].event).toBe("text_delta");
    expect(events[3].event).toBe("turn_done");
  });

  test("yields tool_call and tool_result events", async () => {
    const body = makeStream(
      sseFrame("turn_start", { conversation_id: "c1", message_id: "m2" }),
      sseFrame("tool_call", {
        tool_use_id: "t1",
        tool_name: "coffer__search_memory",
        tool_input: { query: "OAuth" },
      }),
      sseFrame("tool_result", {
        tool_use_id: "t1",
        output: { result: "found it" },
        error: null,
      }),
      sseFrame("text_delta", { text: "Based on your notes..." }),
      sseFrame("turn_done", { message_id: "m2", prompt_tokens: 20, completion_tokens: 10 }),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, body }),
    );

    const events = [];
    for await (const event of streamChatTurn("c1", "what about OAuth?")) {
      events.push(event);
    }

    expect(events).toHaveLength(5);
    expect(events[1].event).toBe("tool_call");
    expect(events[2].event).toBe("tool_result");
    expect(events[3].event).toBe("text_delta");
    expect(events[4].event).toBe("turn_done");
  });

  test("yields turn_error and stops", async () => {
    const body = makeStream(
      sseFrame("turn_start", { conversation_id: "c1", message_id: "m3" }),
      sseFrame("turn_error", { code: "MODEL_UNAVAILABLE", message: "provider error" }),
      // This frame should NOT be yielded — generator must stop after turn_error.
      sseFrame("text_delta", { text: "should not appear" }),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, body }),
    );

    const events = [];
    for await (const event of streamChatTurn("c1", "ping")) {
      events.push(event);
    }

    expect(events).toHaveLength(2);
    expect(events[1].event).toBe("turn_error");
  });

  test("throws ApiError for a 409 HTTP error response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: vi.fn().mockResolvedValue({
          error: { code: "TURN_IN_PROGRESS", message: "a turn is already in progress" },
        }),
      }),
    );

    await expect(async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of streamChatTurn("c1", "hi")) {
        // should not reach here
      }
    }).rejects.toThrow(ApiError);

    try {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of streamChatTurn("c1", "hi")) {
        // do nothing
      }
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).code).toBe("TURN_IN_PROGRESS");
    }
  });

  test("throws ApiError for a 404 HTTP error response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: vi.fn().mockResolvedValue({
          error: { code: "CONVERSATION_NOT_FOUND", message: "not found" },
        }),
      }),
    );

    let thrown: unknown;
    try {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of streamChatTurn("bad-id", "hi")) {
        // do nothing
      }
    } catch (err) {
      thrown = err;
    }

    expect(thrown).toBeInstanceOf(ApiError);
    expect((thrown as ApiError).code).toBe("CONVERSATION_NOT_FOUND");
  });

  test("handles multi-chunk SSE frames split across read() calls", async () => {
    // Split a single SSE frame across two chunks.
    const fullFrame = sseFrame("text_delta", { text: "split" });
    const half = Math.floor(fullFrame.length / 2);
    const chunk1 = fullFrame.slice(0, half);
    const chunk2 = fullFrame.slice(half);

    const body = makeStream(
      sseFrame("turn_start", { conversation_id: "c2", message_id: "m4" }),
      chunk1,
      chunk2,
      sseFrame("turn_done", { message_id: "m4" }),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, body }),
    );

    const events = [];
    for await (const event of streamChatTurn("c2", "test")) {
      events.push(event);
    }

    expect(events).toHaveLength(3);
    expect(events[1].event).toBe("text_delta");
    expect((events[1] as { event: string; data: { text: string } }).data.text).toBe("split");
  });

  test("parses CRLF-separated SSE frames correctly", async () => {
    // Build frames using \r\n line endings and \r\n\r\n frame separators.
    function crlfFrame(event: string, data: unknown): string {
      return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
    }

    const body = makeStream(
      crlfFrame("turn_start", { conversation_id: "c4", message_id: "m6" }),
      crlfFrame("text_delta", { text: "crlf" }),
      crlfFrame("turn_done", { message_id: "m6" }),
    );

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));

    const events = [];
    for await (const event of streamChatTurn("c4", "test")) {
      events.push(event);
    }

    expect(events).toHaveLength(3);
    expect(events[0].event).toBe("turn_start");
    expect(events[1].event).toBe("text_delta");
    expect((events[1] as { event: string; data: { text: string } }).data.text).toBe("crlf");
    expect(events[2].event).toBe("turn_done");
  });

  test("ignores SSE comment/keep-alive lines without breaking parsing", async () => {
    // SSE keep-alive lines start with ':' and should be silently skipped.
    const encoder = new TextEncoder();
    // Manually construct a stream that interleaves a comment line.
    const raw =
      ": keep-alive\n\n" +
      sseFrame("turn_start", { conversation_id: "c5", message_id: "m7" }) +
      ": ping\n\n" +
      sseFrame("text_delta", { text: "after comment" }) +
      sseFrame("turn_done", { message_id: "m7" });

    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(raw));
        controller.close();
      },
    });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body }));

    const events = [];
    for await (const event of streamChatTurn("c5", "test")) {
      events.push(event);
    }

    // Comment frames have no data lines so parseFrame returns null — they are skipped.
    expect(events).toHaveLength(3);
    expect(events[0].event).toBe("turn_start");
    expect(events[1].event).toBe("text_delta");
    expect((events[1] as { event: string; data: { text: string } }).data.text).toBe("after comment");
    expect(events[2].event).toBe("turn_done");
  });

  test("skips frames with an unrecognized event name", async () => {
    // A future/unknown SSE event must not be yielded as a typed AgentEvent.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: makeStream(
          sseFrame("turn_start", {}),
          sseFrame("mystery_event", { foo: "bar" }),
          sseFrame("text_delta", { text: "hi" }),
          sseFrame("turn_done", { stop_reason: "end_turn" }),
        ),
      }),
    );

    const events = [];
    for await (const event of streamChatTurn("c9", "test")) {
      events.push(event);
    }

    expect(events.map((e) => e.event)).toEqual(["turn_start", "text_delta", "turn_done"]);
  });

  test("sends correct headers and body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: makeStream(
        sseFrame("turn_start", { conversation_id: "c3", message_id: "m5" }),
        sseFrame("turn_done", { message_id: "m5" }),
      ),
    });
    vi.stubGlobal("fetch", fetchMock);

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    for await (const _ of streamChatTurn("c3", "hello")) {
      // consume
    }

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/chat/conversations/c3/messages");
    expect(options.method).toBe("POST");
    const headers = options.headers as Record<string, string>;
    expect(headers["X-Coffer-Token"]).toBe("test-token");
    expect(headers["X-Coffer-Actor"]).toBe("ui");
    expect(JSON.parse(options.body as string)).toEqual({ text: "hello" });
  });
});
