// frontend/src/lib/hooks/useChannels.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
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
vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));

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

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

// … while status/pairing use the hand-written fetch module (channels.ts).
function stubFetch(payload: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => payload,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("useChannels hooks", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  test("useChannels lists resources scoped to kind=channel", async () => {
    const api = mockApiClient({
      GET: vi.fn().mockResolvedValue({
        data: {
          resources: [{ kind: "channel", name: "tg", config: { channel_type: "telegram" } }],
        },
        error: undefined,
      }),
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useChannels(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("tg");
    expect(api.GET).toHaveBeenCalledWith("/resources", {
      params: { query: { kind: "channel" } },
    });
  });

  test("useChannelStatus fetches /channels/{name}/status", async () => {
    const status: ChannelStatus = {
      name: "tg",
      channel_type: "telegram",
      enabled: true,
      running: true,
      pending_pairing: false,
      peer: null,
      callback: null,
      runs_on: "machine-here",
      runs_here: true,
    };
    const fetchMock = stubFetch(status);

    const { result } = renderHook(() => useChannelStatus("tg"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.running).toBe(true);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/channels/tg/status");
  });

  test("useIssuePairingCode POSTs and returns the code", async () => {
    const code: PairingCode = { code: "ABCD2345", expires_at: "2026-06-12T13:00:00Z" };
    const fetchMock = stubFetch(code);

    const { result } = renderHook(() => useIssuePairingCode("tg"), { wrapper: makeWrapper() });
    act(() => result.current.mutate());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.code).toBe("ABCD2345");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/channels/tg/pairing-code");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });

  test("useRebindChannel PATCHes the config with the new binding, keeping the rest", async () => {
    // A rebind is an ordinary config edit — there is no command reaching
    // across to the other machine — so every other field has to survive it.
    // Dropping a credential ref here would move the channel and break it in
    // the same request.
    const api = mockApiClient();
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);

    const { result } = renderHook(() => useRebindChannel("tg"), { wrapper: makeWrapper() });
    act(() =>
      result.current.mutate({
        config: { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" },
        runsOn: "machine-there",
        machine: "Desktop",
      }),
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.PATCH).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "channel", name: "tg" } },
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
    stubFetch({ error: { code: "ADAPTER_OFFLINE", message: "adapter offline" } }, false, 500);

    const { result } = renderHook(() => useIssuePairingCode("tg"), { wrapper: makeWrapper() });
    act(() => result.current.mutate());

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(errorToast).toHaveBeenCalledTimes(1);
    expect(errorToast).toHaveBeenCalledWith(expect.stringContaining("adapter offline"));
  });
});

describe("useCreateChannel", () => {
  beforeEach(() => vi.clearAllMocks());

  test("registers the channel and refreshes the resources cache", async () => {
    const api = mockApiClient();
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useCreateChannel(), {
      wrapper: ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      ),
    });

    await act(async () => {
      await result.current.mutateAsync({
        name: "tg",
        secrets: [{ ref: "channel/tg/bot-token", value: "123:abc" }],
        config: { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" },
      });
    });

    expect(api.POST.mock.calls.map((c) => c[0])).toEqual(["/credentials", "/resources"]);
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: resourcesKey }),
      ),
    );
  });

  test("toasts when registration fails", async () => {
    const api = mockApiClient({
      POST: vi.fn(async (path: string) =>
        path === "/resources"
          ? { error: { error: { code: "CONFIG_INVALID", message: "bad config" } } }
          : { data: undefined, error: undefined },
      ) as ReturnType<typeof mockApiClient>["POST"],
    });
    getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
    const { result } = renderHook(() => useCreateChannel(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current
        .mutateAsync({ name: "tg", secrets: [], config: { channel_type: "telegram" } })
        .catch(() => undefined);
    });

    await waitFor(() => expect(errorToast).toHaveBeenCalled());
  });
});
