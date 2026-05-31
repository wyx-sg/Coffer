// frontend/src/lib/api/chat.test.ts
//
// Covers the hand-rolled SSE parser in streamMessage(): the repo deliberately
// avoids @microsoft/fetch-event-source, so the `data: <json>` frame splitting
// is load-bearing and exercised directly here, including frames that arrive
// split across chunk boundaries and a trailing frame with no final blank line.
import { afterEach, describe, expect, test, vi } from "vitest";

import { chatApi, streamMessage, type ChatStreamEvent } from "./chat";
import { ApiError } from "./errors";

/** Build a Response whose body streams the given chunks as a ReadableStream. */
function sseResponse(chunks: string[], ok = true, status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(ok ? body : null, { status });
}

afterEach(() => vi.restoreAllMocks());

describe("streamMessage", () => {
  test("parses data: frames and delivers each event in order", async () => {
    const frames = [
      'data: {"type":"text_delta","text":"Hel"}\n\n',
      'data: {"type":"text_delta","text":"lo"}\n\n',
      'data: {"type":"tool_call","id":"t1","tool":"shell","args":{"cmd":"ls"}}\n\n',
      'data: {"type":"tool_result","id":"t1","tool":"shell","ok":true,"summary":"ok"}\n\n',
      'data: {"type":"done"}\n\n',
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(frames));

    const events: ChatStreamEvent[] = [];
    await streamMessage("c1", "hi", (e) => events.push(e));

    expect(events.map((e) => e.type)).toEqual([
      "text_delta",
      "text_delta",
      "tool_call",
      "tool_result",
      "done",
    ]);
    expect(events[0]).toMatchObject({ type: "text_delta", text: "Hel" });
  });

  test("reassembles a frame split across chunk boundaries", async () => {
    // One logical frame arrives as three separate stream chunks.
    const chunks = ['data: {"type":"text', '_delta","text":"hi"}', "\n\n"];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(chunks));

    const events: ChatStreamEvent[] = [];
    await streamMessage("c1", "hi", (e) => events.push(e));

    expect(events).toEqual([{ type: "text_delta", text: "hi" }]);
  });

  test("flushes a trailing frame with no final blank line", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(['data: {"type":"done"}']));

    const events: ChatStreamEvent[] = [];
    await streamMessage("c1", "hi", (e) => events.push(e));

    expect(events).toEqual([{ type: "done" }]);
  });

  test("ignores non-JSON / keep-alive frames", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse([": keep-alive\n\n", 'data: {"type":"done"}\n\n']),
    );

    const events: ChatStreamEvent[] = [];
    await streamMessage("c1", "hi", (e) => events.push(e));

    expect(events).toEqual([{ type: "done" }]);
  });

  test("maps a non-2xx pre-stream response to an ApiError", async () => {
    const errResponse = new Response(
      JSON.stringify({ error: { code: "CONVERSATION_BUSY", message: "busy" } }),
      { status: 409 },
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue(errResponse);

    await expect(streamMessage("c1", "hi", () => {})).rejects.toBeInstanceOf(ApiError);
  });
});

describe("chatApi", () => {
  test("list() encodes the status / limit / offset query", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));

    await chatApi.list("archived", 10, 20);

    const url = spy.mock.calls[0][0] as string;
    expect(url).toContain("/conversations?");
    expect(url).toContain("status=archived");
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=20");
  });

  test("stop() returns on a 204 with no body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(chatApi.stop("c1")).resolves.toBeUndefined();
  });

  test("confirm() throws an ApiError on a non-2xx envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "gone" } }), {
        status: 404,
      }),
    );
    await expect(chatApi.confirm("c1", { request_id: "r1", approve: true })).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});
