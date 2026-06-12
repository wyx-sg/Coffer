// frontend/src/lib/hooks/useMemoryProjections.test.tsx
//
// Exercises the memory store + projection query/mutation bindings (spec 007).
// The kinds/memory API module is mocked so each hook's queryFn/mutationFn and
// its invalidation behavior can be asserted without a backend.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import {
  useEstablishProjection,
  useMemoryProjections,
  useMemoryStores,
  useRemoveProjection,
} from "./useMemoryProjections";

vi.mock("@/kinds/memory/api", () => ({
  listMemoryStores: vi.fn(),
  listProjections: vi.fn(),
  establishProjection: vi.fn(),
  removeProjection: vi.fn(),
}));
const api = await import("@/kinds/memory/api");

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

const STORE = {
  ref: "memory:global",
  kind: "memory",
  name: "global",
  scope: "global" as const,
  project_id: "00000000000000000000000000",
  project_root: null,
  description: null,
  config: {
    retrieval_modes: ["grep", "keyword"] as ("grep" | "keyword" | "vector")[],
    default_mode: "keyword" as const,
    embedding_dimensions: 768,
    max_fact_chars: 8192,
  },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const PROJECTION = {
  agent_ref: "agent:claude-code",
  projection_mode: "SYMLINK" as const,
  target_path: "/Users/dev/.claude/memory",
  native_memory_disabled: false,
  merged_existing: false,
};

beforeEach(() => vi.clearAllMocks());

describe("useMemoryStores", () => {
  test("unwraps memory_stores from the list response", async () => {
    vi.mocked(api.listMemoryStores).mockResolvedValue({
      memory_stores: [STORE],
      total: 1,
    } as Awaited<ReturnType<typeof api.listMemoryStores>>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMemoryStores(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([STORE]);
  });
});

describe("useMemoryProjections", () => {
  test("unwraps projections for the given store", async () => {
    vi.mocked(api.listProjections).mockResolvedValue({
      projections: [PROJECTION],
      total: 1,
    } as Awaited<ReturnType<typeof api.listProjections>>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMemoryProjections("global"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.listProjections).toHaveBeenCalledWith("global");
    expect(result.current.data).toEqual([PROJECTION]);
  });

  test("stays disabled (no fetch) when the store name is empty", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMemoryProjections(""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(api.listProjections).not.toHaveBeenCalled();
  });
});

describe("useEstablishProjection", () => {
  test("calls establishProjection with agentRef + projectRoot and invalidates", async () => {
    vi.mocked(api.establishProjection).mockResolvedValue(
      PROJECTION as Awaited<ReturnType<typeof api.establishProjection>>,
    );

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEstablishProjection("global"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        agentRef: "agent:claude-code",
        projectRoot: "/repo",
      });
    });

    expect(api.establishProjection).toHaveBeenCalledWith("global", "agent:claude-code", "/repo");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["memory-projections", "global"] });
  });
});

describe("useRemoveProjection", () => {
  test("calls removeProjection with the agent ref and invalidates", async () => {
    vi.mocked(api.removeProjection).mockResolvedValue(undefined);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRemoveProjection("global"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("agent:claude-code");
    });

    expect(api.removeProjection).toHaveBeenCalledWith("global", "agent:claude-code");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["memory-projections", "global"] });
  });
});
