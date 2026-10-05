// The cross-agent session listing over the typed client: what goes on the wire.
import { afterEach, beforeEach, describe, expect, test, vi, type MockInstance } from "vitest";

import { agentSessionsApi } from "./agentSessions";
import { resetApiClient } from "./client";
import { ApiError } from "./errors";

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

describe("agentSessionsApi.listAll", () => {
  test("reads one page by limit, cursor, search, sources and agents", async () => {
    fetchSpy.mockResolvedValueOnce(json({ sessions: [], next_cursor: "c1", unavailable: [] }));

    const out = await agentSessionsApi.listAll({
      limit: 50,
      cursor: "c0",
      q: "deploy",
      source: ["local", "ch1"],
      agent: ["codex"],
    });

    expect(out.next_cursor).toBe("c1");
    const url = new URL(requestAt(0).url);
    expect(url.pathname).toBe("/api/v1/agent-sessions");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("cursor")).toBe("c0");
    expect(url.searchParams.get("q")).toBe("deploy");
    expect(url.searchParams.get("source")).toBe("local,ch1");
    expect(url.searchParams.get("agent")).toBe("codex");
  });

  test("leaves out what it was not given", async () => {
    fetchSpy.mockResolvedValueOnce(json({ sessions: [], next_cursor: null, unavailable: [] }));
    await agentSessionsApi.listAll({ limit: 30 });
    const url = new URL(requestAt(0).url);
    for (const key of ["cursor", "q", "source", "agent"])
      expect(url.searchParams.has(key)).toBe(false);
  });

  test("surfaces a failure as an ApiError", async () => {
    fetchSpy.mockImplementation(async () =>
      json({ error: { code: "CURSOR_INVALID", message: "x" } }, 400),
    );
    await expect(agentSessionsApi.listAll({ limit: 30 })).rejects.toBeInstanceOf(ApiError);
  });
});
