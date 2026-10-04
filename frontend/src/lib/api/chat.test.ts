// The chat request functions over the typed client: what goes on the wire (URL,
// method, body) and the cursor walk of the conversation listing.
import { afterEach, beforeEach, describe, expect, test, vi, type MockInstance } from "vitest";

import { chatApi } from "./chat";
import { resetApiClient } from "./client";
import { ApiError } from "./errors";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const row = (id: string) => ({ id });

let fetchSpy: MockInstance<typeof fetch>;

beforeEach(() => {
  (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__ =
    "http://127.0.0.1:38470/api/v1";
  resetApiClient();
  fetchSpy = vi.spyOn(globalThis, "fetch");
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__;
  resetApiClient();
  vi.restoreAllMocks();
});

const requestAt = (n: number) => fetchSpy.mock.calls[n][0] as Request;

describe("chatApi.listConversations", () => {
  test("reads one page by limit, cursor, archived flag and title search", async () => {
    fetchSpy.mockResolvedValueOnce(json({ conversations: [row("a")], next_cursor: "c1" }));

    const out = await chatApi.listConversations({
      archived: true,
      limit: 50,
      cursor: "c0",
      q: "deploy",
    });

    expect(out.conversations.map((c) => c.id)).toEqual(["a"]);
    expect(out.next_cursor).toBe("c1");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const url = new URL(requestAt(0).url);
    expect(url.pathname).toBe("/api/v1/chat/conversations");
    expect(url.searchParams.get("archived")).toBe("true");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("cursor")).toBe("c0");
    expect(url.searchParams.get("q")).toBe("deploy");
  });

  test("leaves out a cursor and a search it was not given", async () => {
    fetchSpy.mockResolvedValueOnce(json({ conversations: [], next_cursor: null }));

    await chatApi.listConversations({ limit: 30 });

    const url = new URL(requestAt(0).url);
    expect(url.searchParams.get("archived")).toBe("false");
    expect(url.searchParams.has("cursor")).toBe(false);
    expect(url.searchParams.has("q")).toBe(false);
  });

  test("aborts the request with the signal it was given", async () => {
    fetchSpy.mockImplementation(
      (input) =>
        new Promise((_, reject) => {
          const signal = (input as Request).signal;
          const abort = () => reject(new DOMException("aborted", "AbortError"));
          if (signal.aborted) abort();
          else signal.addEventListener("abort", abort);
        }),
    );
    const controller = new AbortController();
    const pending = chatApi.listConversations({ limit: 30 }, controller.signal);
    controller.abort();
    await expect(pending).rejects.toBeDefined();
  });

  test("surfaces a failure as an ApiError", async () => {
    fetchSpy.mockImplementation(async () =>
      json({ error: { code: "CURSOR_INVALID", message: "x" } }, 400),
    );
    await expect(chatApi.listConversations({ limit: 30 })).rejects.toMatchObject({
      code: "CURSOR_INVALID",
    });
    await expect(chatApi.listConversations({ limit: 30 })).rejects.toBeInstanceOf(ApiError);
  });
});

describe("chatApi requests", () => {
  test("setPending PUTs the queue and returns the stored one", async () => {
    fetchSpy.mockResolvedValue(json({ pending: ["b"] }));

    const out = await chatApi.setPending("c1", ["b"]);

    expect(out).toEqual({ pending: ["b"] });
    const req = requestAt(0);
    expect(req.method).toBe("PUT");
    expect(new URL(req.url).pathname).toBe("/api/v1/chat/conversations/c1/pending");
    expect(await req.clone().json()).toEqual({ pending: ["b"] });
  });

  test("sendMessage carries attachment ids only when there are some", async () => {
    fetchSpy.mockImplementation(async () => json({ queued: false, mirror: null }, 202));

    await chatApi.sendMessage("c1", "hi");
    await chatApi.sendMessage("c1", "hi", ["a1"]);

    expect(await requestAt(0).clone().json()).toEqual({ text: "hi" });
    expect(await requestAt(1).clone().json()).toEqual({ text: "hi", attachment_ids: ["a1"] });
  });

  test("uploadAttachment sends the file as multipart form data", async () => {
    fetchSpy.mockResolvedValue(json({ id: "u1", name: "a.txt" }));

    await chatApi.uploadAttachment(new File(["hi"], "a.txt", { type: "text/plain" }));

    const req = requestAt(0);
    expect(req.method).toBe("POST");
    expect(req.headers.get("content-type")).toMatch(/^multipart\/form-data; boundary=/);
  });

  test("deleteConversation and interruptTurn resolve on 204", async () => {
    fetchSpy.mockImplementation(async () => new Response(null, { status: 204 }));

    await expect(chatApi.deleteConversation("c1")).resolves.toBeUndefined();
    await expect(chatApi.interruptTurn("c1")).resolves.toBeUndefined();
    expect(requestAt(0).method).toBe("DELETE");
    expect(new URL(requestAt(1).url).pathname).toBe("/api/v1/chat/conversations/c1/interrupt");
  });
});
