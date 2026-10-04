// src/lib/events/eventStream.test.ts — reading GET /api/v1/events and staying connected.
import { afterEach, expect, test, vi } from "vitest";

import {
  followDaemonEvents,
  frameToMessage,
  parseSseBlock,
  type StreamMessage,
} from "./eventStream";

afterEach(() => {
  vi.unstubAllGlobals();
  delete (window as unknown as { __COFFER_BASE_URL__?: string }).__COFFER_BASE_URL__;
});

test("a change block parses into its envelope and SSE id", () => {
  const frame = parseSseBlock(
    'event: change\nid: run1.7\ndata: {"seq":7,"kind":"attention","id":null,"op":"upsert"}',
  );
  expect(frame).toEqual({
    event: "change",
    id: "run1.7",
    data: '{"seq":7,"kind":"attention","id":null,"op":"upsert"}',
  });
  expect(frameToMessage(frame!)).toEqual({
    type: "change",
    change: { seq: 7, kind: "attention", id: null, op: "upsert" },
  });
});

test("resync and heartbeat are recognised; comments and junk are not", () => {
  expect(frameToMessage(parseSseBlock('event: resync\ndata: {"seq":3}')!)).toEqual({
    type: "resync",
  });
  expect(frameToMessage(parseSseBlock('event: heartbeat\ndata: {"seq":3}')!)).toEqual({
    type: "heartbeat",
    seq: 3,
  });
  expect(parseSseBlock(": ping")).toBeNull();
  expect(frameToMessage({ event: "change", data: "not json", id: null })).toBeNull();
});

function streamOf(text: string): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

test("a reconnect sends the last change's id as Last-Event-ID", async () => {
  (window as unknown as { __COFFER_BASE_URL__?: string }).__COFFER_BASE_URL__ =
    "http://daemon/api/v1";
  const controller = new AbortController();
  const seen: StreamMessage[] = [];
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      streamOf(
        'event: change\nid: r.4\ndata: {"seq":4,"kind":"mcp_server","id":"u","op":"upsert"}\n\n',
      ),
    )
    .mockImplementationOnce(async (_url: string, init: RequestInit) => {
      controller.abort();
      expect((init.headers as Record<string, string>)["Last-Event-ID"]).toBe("r.4");
      return streamOf("");
    });
  vi.stubGlobal("fetch", fetchMock);
  vi.useFakeTimers();
  const run = followDaemonEvents((m) => seen.push(m), controller.signal);
  await vi.runAllTimersAsync();
  await run;
  vi.useRealTimers();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(seen.map((m) => m.type)).toEqual(["open", "change", "closed"]);
  expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
    "X-Coffer-Actor": "ui",
  });
});
