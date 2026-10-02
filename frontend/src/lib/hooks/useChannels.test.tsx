// frontend/src/lib/hooks/useChannels.test.tsx
//
// Every hook here that names one channel takes its `uid`: the status, pairing
// and notify routes are `/channels/{uid}/…`, and a rebind is a PATCH of
// `/resources/{uid}`. The name travels beside it only where a person reads it
// (the rebind toast), which is why `useRebindChannel` takes both and the
// fixtures below spell the two differently.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import {
  useChannels,
  useChannelStatus,
  useCreateChannel,
  useIssuePairingCode,
  useRebindChannel,
} from "./useChannels";
import { mockApiClient } from "@/test/mockApiClient";
import { resourcesKey } from "@/lib/api/queryKeys";
import type { ChannelStatus, PairingCode } from "@/lib/api/channels";

// useChannels rides the generic resources API (openapi-fetch client) …
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));

// onError → toast is the default for every mutation (.agents/frontend.md §5):
// a failed pairing-code issue must announce itself, not fail silently.
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

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

/** The channel every case below is about: addressed by uid, read as "tg". */
const TG = { uid: "u-3d9a1f77", name: "tg" };

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

/** The typed client answering one route with `data` (2xx) or an envelope (non-2xx). */
function stubApi(data: unknown) {
  const api = mockApiClient({
    GET: vi.fn().mockResolvedValue({ data, error: undefined }),
    POST: vi.fn().mockResolvedValue({ data, error: undefined }),
  });
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

describe("useChannels hooks", () => {
  beforeEach(() => vi.clearAllMocks());

  test("useChannels lists resources scoped to kind=channel", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: {
          resources: [{ ...TG, kind: "channel", config: { channel_type: "telegram" } }],
        },
        error: undefined,
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useChannels(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe(TG.name);
    expect(result.current.data?.[0].uid).toBe(TG.uid);
    expect(api.GET).toHaveBeenCalledWith("/resources", {
      params: { query: { kind: "channel" } },
    });
  });

  test("useChannelStatus fetches /channels/{uid}/status", async () => {
    const status: ChannelStatus = {
      ...TG,
      title: null,
      channel_type: "telegram",
      diagnostics: [],
      enabled: true,
      running: true,
      pending_pairing: false,
      peer: null,
      inbound: null,
      runs_on: "machine-here",
      runs_here: true,
      handoff: null,
      settings: null,
    };
    const api = stubApi(status);

    const { result } = renderHook(() => useChannelStatus(TG.uid), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.running).toBe(true);
    expect(api.GET).toHaveBeenCalledWith("/channels/{uid}/status", {
      params: { path: { uid: TG.uid } },
    });
  });

  test("useIssuePairingCode POSTs and returns the code", async () => {
    const code: PairingCode = {
      code: "ABCD2345",
      expires_at: "2026-06-12T13:00:00Z",
      pair_url: "",
    };
    const api = stubApi(code);

    const { result } = renderHook(() => useIssuePairingCode(TG.uid), { wrapper: makeWrapper() });
    act(() => result.current.mutate());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.code).toBe("ABCD2345");
    expect(api.POST).toHaveBeenCalledWith("/channels/{uid}/pairing-code", {
      params: { path: { uid: TG.uid } },
    });
  });

  test("useRebindChannel PATCHes the config with the new binding, keeping the rest", async () => {
    // A rebind is an ordinary config edit — there is no command reaching
    // across to the other machine — so every other field has to survive it.
    // Dropping a secret ref here would move the channel and break it in
    // the same request.
    const api = mockApiClient();
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useRebindChannel(TG.uid, TG.name), {
      wrapper: makeWrapper(),
    });
    act(() =>
      result.current.mutate({
        config: { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" },
        runsOn: "machine-there",
        machine: "Desktop",
      }),
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{uid}", {
      params: { path: { uid: TG.uid } },
      body: {
        config: {
          channel_type: "telegram",
          bot_token_ref: "channel/tg/bot-token",
          runs_on: "machine-there",
        },
      },
    });
  });

  test("useIssuePairingCode toasts an error when the request fails (not silent)", async () => {
    // An unmapped error code falls through to the server envelope message,
    // so the toast carries the real failure reason rather than being silent.
    const api = mockApiClient({
      POST: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "ADAPTER_OFFLINE", message: "adapter offline" } },
        response: new Response(null, { status: 500 }),
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useIssuePairingCode(TG.uid), { wrapper: makeWrapper() });
    act(() => result.current.mutate());

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(errorToast).toHaveBeenCalledTimes(1);
    expect(errorToast).toHaveBeenCalledWith(expect.stringContaining("adapter offline"));
  });
});

describe("useCreateChannel", () => {
  beforeEach(() => vi.clearAllMocks());

  /** The api client with `POST /resources` answering as the daemon does: the
   *  row it created, uid and all. The create resolves with that resource — the
   *  caller needs the uid for the link and the name for the toast, and they
   *  are no longer the same string. */
  function registeringApi() {
    return mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { resources: [] }, error: undefined }),
      POST: vi.fn(async (path: string, init?: unknown) =>
        path === "/resources"
          ? { data: { uid: TG.uid, ...(init as { body: Record<string, unknown> }).body } }
          : { data: undefined, error: undefined },
      ) as ReturnType<typeof mockApiClient>["POST"],
    });
  }

  const plan = {
    name: TG.name,
    secrets: [{ ref: "channel/tg/bot-token", value: "123:abc" }],
    config: { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" },
  };

  test("registers the channel, resolves with the resource, refreshes the cache", async () => {
    const api = registeringApi();
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCreateChannel(), {
      wrapper: ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      ),
    });

    let created: { uid: string; name: string } | undefined;
    await act(async () => {
      created = await result.current.mutateAsync(plan);
    });

    // The free-name check first — a scan of the list, because a resource has no
    // by-name lookup route any more — then the secret, then the resource.
    expect(api.GET).toHaveBeenCalledWith("/resources", {
      params: { query: { kind: "channel" } },
    });
    expect(api.POST.mock.calls.map((c) => c[0])).toEqual(["/secrets", "/resources"]);
    expect(created).toMatchObject({ uid: TG.uid, name: TG.name });
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: resourcesKey }),
      ),
    );
  });

  test("a name another channel already holds is stepped past, never refused", async () => {
    // The person typed a display name; the resource name is Coffer's to pick,
    // so a clash with another channel's name moves to the next free one rather
    // than failing the add.
    const api = registeringApi();
    api.GET.mockResolvedValue({
      data: { resources: [{ uid: "u-someone-else", kind: "channel", name: TG.name }] },
      error: undefined,
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
    const { result } = renderHook(() => useCreateChannel(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.mutateAsync(plan);
    });

    const register = api.POST.mock.calls.find((c) => c[0] === "/resources");
    const body = (register?.[1] as { body: Record<string, unknown> }).body;
    expect(body.name).toBe(`${TG.name}-2`);
    expect(body.title).toBe(plan.name);
  });

  test("toasts when registration fails", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({ data: { resources: [] }, error: undefined }),
      POST: vi.fn(async (path: string) =>
        path === "/resources"
          ? {
              error: { error: { code: "CONFIG_INVALID", message: "bad config" } },
              response: new Response(null, { status: 422 }),
            }
          : { data: undefined, error: undefined },
      ) as ReturnType<typeof mockApiClient>["POST"],
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
    const { result } = renderHook(() => useCreateChannel(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current
        .mutateAsync({ name: TG.name, secrets: [], config: { channel_type: "telegram" } })
        .catch(() => undefined);
    });

    await waitFor(() => expect(errorToast).toHaveBeenCalled());
  });
});
