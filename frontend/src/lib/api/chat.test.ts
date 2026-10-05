// The chat request functions over the typed client: what goes on the wire (URL,
// method, body) of a conversation's rename, delete and interrupt.
import { afterEach, beforeEach, describe, expect, test, vi, type MockInstance } from "vitest";

import { chatApi } from "./chat";
import { resetApiClient } from "./client";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

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

describe("chatApi requests", () => {
  test("renameConversation PATCHes the title", async () => {
    fetchSpy.mockResolvedValue(json({ id: "c1", title: "New name" }));

    const out = await chatApi.renameConversation("c1", "New name");

    expect(out.title).toBe("New name");
    const req = requestAt(0);
    expect(req.method).toBe("PATCH");
    expect(new URL(req.url).pathname).toBe("/api/v1/chat/conversations/c1");
    expect(await req.clone().json()).toEqual({ title: "New name" });
  });

  test("deleteConversation and interruptTurn resolve on 204", async () => {
    fetchSpy.mockImplementation(async () => new Response(null, { status: 204 }));

    await expect(chatApi.deleteConversation("c1")).resolves.toBeUndefined();
    await expect(chatApi.interruptTurn("c1")).resolves.toBeUndefined();
    expect(requestAt(0).method).toBe("DELETE");
    expect(new URL(requestAt(1).url).pathname).toBe("/api/v1/chat/conversations/c1/interrupt");
  });
});
