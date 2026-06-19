// frontend/src/lib/hooks/useAgentChatHistory.test.tsx
//
// TanStack Query bindings for the agent transcript distillation endpoints.
// Stubs globalThis.fetch directly because the api module uses plain fetch.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { transcriptsKey, useAgentTranscripts, useDistillTranscript } from "./useAgentChatHistory";

// onError → toast is the default for every mutation (agents/frontend.md §5).
const errorToast = vi.fn();
vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return {
    ...actual,
    useToast: () => ({
      toast: { error: errorToast, success: vi.fn(), info: vi.fn() },
      dismiss: vi.fn(),
    }),
  };
});

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SAMPLE_SESSION = {
  session_id: "s1",
  project_path: "/home/u/repo",
  message_count: 3,
  started_at: "2026-06-01T00:00:00Z",
};

const SAMPLE_DISTILL = {
  insights: [
    {
      name: "Use Redis",
      description: "cache layer",
      body: "We chose Redis for caching.",
      type: "decision",
    },
  ],
  fact_ids: ["fact-1"],
};

describe("transcriptsKey", () => {
  test("returns the expected hierarchical query key", () => {
    expect(transcriptsKey("claude")).toEqual(["agents", "claude", "conversations"]);
  });
});

describe("useAgentTranscripts", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  test("fetches sessions from GET /api/v1/agents/{name}/transcripts", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { sessions: [SAMPLE_SESSION] }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentTranscripts("claude"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.sessions).toHaveLength(1);
    expect(result.current.data?.sessions[0].session_id).toBe("s1");
    const url = String(fetchMock.mock.calls[0][0]);
    // The base URL already carries the /api/v1 prefix; the path must not repeat
    // it (a doubled /api/v1/api/v1 hits no route → 404 NOT_FOUND).
    expect(url).not.toContain("/api/v1/api/v1");
    // Listing is paged (most-recent first) — the request carries limit/offset.
    expect(url).toMatch(/\/api\/v1\/agents\/claude\/transcripts\?limit=\d+&offset=\d+$/);
  });

  test("is disabled when name is empty", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentTranscripts(""), { wrapper: wrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("propagates a non-2xx error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(500, { error: { code: "ERR", message: "boom" } })),
    );
    const { result } = renderHook(() => useAgentTranscripts("claude"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("boom");
  });
});

describe("useDistillTranscript", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  test("POSTs to /api/v1/agents/{name}/transcripts/distill and returns insights", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, SAMPLE_DISTILL));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useDistillTranscript("claude"), {
      wrapper: wrapper(),
    });
    let data: typeof SAMPLE_DISTILL | undefined;
    await act(async () => {
      data = await result.current.mutateAsync({ session_id: "s1" });
    });
    expect(data?.insights).toHaveLength(1);
    expect(data?.fact_ids).toEqual(["fact-1"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).not.toContain("/api/v1/api/v1");
    expect(String(url)).toMatch(/\/api\/v1\/agents\/claude\/transcripts\/distill$/);
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ session_id: "s1" });
  });

  test("calls toast.error on mutation failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(500, { error: { code: "ERR", message: "kaboom" } })),
    );
    const { result } = renderHook(() => useDistillTranscript("claude"), {
      wrapper: wrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ session_id: "s1" }).catch(() => {});
    });
    await waitFor(() => expect(errorToast).toHaveBeenCalled());
  });
});
