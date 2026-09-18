// frontend/src/lib/hooks/useResources.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useKindReach, useResource, useResources } from "./useResources";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

/** One resource's uid and the label it wears. Kept unalike on purpose: the
 *  whole point of the uid is that it survives the label changing, so a fixture
 *  where the two coincide could not tell a hook reading the wrong one. */
const FS_UID = "u-mcp-9f2c";

/** A full `ResourceOut` row, as `GET /resources` returns it. */
function row(overrides: Record<string, unknown> = {}) {
  return {
    uid: FS_UID,
    kind: "mcp_server",
    name: "fs",
    description: null,
    config: {},
    enabled: true,
    created_at: "2026-05-21T00:00:00Z",
    updated_at: "2026-05-21T00:00:00Z",
    ...overrides,
  };
}

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useResources", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("returns the resources array on success", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: { resources: [row()] },
        error: undefined,
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useResources("mcp_server"), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toHaveLength(1);
    // Both halves come through: the identity the app addresses the row by, and
    // the label it shows the user.
    expect(result.current.data?.[0].uid).toBe(FS_UID);
    expect(result.current.data?.[0].name).toBe("fs");
  });

  test("throws on API error", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "BOOM", message: "kaboom" } },
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useResources(), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect((result.current.error as Error).message).toContain("kaboom");
  });
});

describe("useResource", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches one row by uid, with no kind in the path", async () => {
    // The uid names exactly one resource, and the row it returns says what
    // kind it is — so the caller no longer has to know the kind to ask.
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: row(), error: undefined }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useResource(FS_UID), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.GET).toHaveBeenCalledWith(
      "/resources/{uid}",
      expect.objectContaining({ params: { path: { uid: FS_UID } } }),
    );
    expect(result.current.data?.kind).toBe("mcp_server");
  });

  test("is idle for an empty uid rather than requesting one", () => {
    const api = mockApiClient({ GET: vi.fn() });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useResource(""), { wrapper: wrapper() });

    expect(result.current.fetchStatus).toBe("idle");
    expect(api.GET).not.toHaveBeenCalled();
  });
});

describe("useKindReach", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("keys the reach merge on the uid, not the label", async () => {
    // The dedicated per-kind list endpoints (`/knowledge/collections`,
    // `/providers`, `/memory/partitions`) carry no `enabled`/`scope`, so the
    // table merges them in from `GET /resources?kind=…`. Joining on the NAME
    // would make that merge depend on both lists having been read at the same
    // instant: a rename in between would find no match and silently drop the
    // row's reach back to its default.
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: {
          resources: [row({ enabled: false, scope: { agents: ["u-agent-7f21"] } })],
        },
        error: undefined,
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useKindReach("mcp_server"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.size).toBe(1));
    expect(result.current.get(FS_UID)).toEqual({
      enabled: false,
      scope: { agents: ["u-agent-7f21"] },
    });
    expect(result.current.has("fs")).toBe(false);
  });
});
