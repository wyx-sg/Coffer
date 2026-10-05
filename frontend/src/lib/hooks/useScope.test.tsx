// frontend/src/lib/hooks/useScope.test.tsx
//
// The scope query and its write, pinned at the wire: the route takes the
// resource's UID and nothing else (no kind segment), and the cache key it
// invalidates is keyed on that same uid. Both matter because a name is now a
// mutable label — a request or a key built from one would stop naming the same
// row the moment a user renamed it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { resetApiClient } from "@/lib/api/client";
import type { PropsWithChildren } from "react";

import { useResourceScope, useUpdateResourceScope } from "./useScope";
import type { ResourceScope } from "@/lib/api/scope";
import { ApiError } from "@/lib/api/errors";

/** The uid and the name of the same resource. They are deliberately unalike:
 *  an assertion that reached for the wrong one has to fail, not coincide. */
const FS_UID = "u-mcp-9f2c";
const WRITING_UID = "u-skill-4e8d";

/** One registered agent, as a scope stores it — a uid, never the name the
 *  picker prints beside it. */
const CLAUDE = "u-agent-7f21";

/** A literal in the wire's spelling, typed as the generated `ResourceScopeOut`, so a field renamed on the backend fails `npm run typecheck`. */
const resourceScopeContract: ResourceScope = {
  scope: { agents: [CLAUDE] },
  supports_scope: true,
};

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

function stubFetch(payload: unknown, status = 200) {
  // A fresh Response per call: the typed client reads the body, which a
  // single shared one allows only once.
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  // The client binds `fetch` when it is built, so a stub needs a fresh one.
  resetApiClient();
  return fetchMock;
}

describe("useResourceScope", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("fetches GET /resources/{uid}/scope", async () => {
    const fetchMock = stubFetch(resourceScopeContract);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useResourceScope(FS_UID), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(resourceScopeContract);
    // The uid alone addresses the row: there is no kind segment left to get
    // wrong, and the name never reaches the wire.
    expect((fetchMock.mock.calls[0][0] as Request).url).toMatch(
      new RegExp(`/resources/${FS_UID}/scope$`),
    );
  });

  test("is disabled for an empty uid", () => {
    const fetchMock = stubFetch({});
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useResourceScope(""), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("a caller that already holds the scope can switch the query off", () => {
    // The list tables pass `ResourceOut.scope` straight through rather than
    // mounting one GET per row; `enabled` is the second argument.
    const fetchMock = stubFetch(resourceScopeContract);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useResourceScope(FS_UID, false), { wrapper });

    expect(result.current.fetchStatus).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useUpdateResourceScope", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("PUTs the scope body to /resources/{uid}/scope", async () => {
    const fetchMock = stubFetch({
      uid: FS_UID,
      kind: "mcp_server",
      name: "fs",
      config: {},
      scope: { agents: [CLAUDE] },
      enabled: true,
      created_at: "2026-07-10T00:00:00Z",
      updated_at: "2026-07-10T00:00:00Z",
    });

    const { wrapper } = makeWrapper();
    // `kind` is carried for the invalidation below, never for the request.
    const { result } = renderHook(() => useUpdateResourceScope("mcp_server", FS_UID), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ agents: [CLAUDE] });
    });

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toMatch(new RegExp(`/resources/${FS_UID}/scope$`));
    expect(request.method).toBe("PUT");
    // The body names agents by uid, which is what the picker ticks write.
    expect(await request.clone().json()).toEqual({
      scope: { agents: [CLAUDE] },
    });
  });

  test("invalidates the scope key and the agent list on success", async () => {
    stubFetch({ scope: null });

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateResourceScope("skill", WRITING_UID), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ agents: ["u-agent-1"] });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    // Keyed on the uid and nothing else: the kind is not a segment, so the
    // entry stays the same entry across a rename.
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["scope", WRITING_UID] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["agents"] }));
    // …and the kind's own list, which is the only thing `kind` is here for.
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["skills"] }));
  });

  test("surfaces an ApiError when the PUT fails", async () => {
    stubFetch({ error: { code: "RESOURCE_NOT_FOUND", message: "not found" } }, 404);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateResourceScope("mcp_server", "u-mcp-missing"), {
      wrapper,
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({ agents: ["u-agent-1"] });
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("RESOURCE_NOT_FOUND");
  });
});
