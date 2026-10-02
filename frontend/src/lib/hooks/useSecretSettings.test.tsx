// frontend/src/lib/hooks/useSecretSettings.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { useSecretSettings, useUpdateSecretSettings } from "./useSecretSettings";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

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

describe("useSecretSettings", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns settings on success", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: { master_key_storage: "file" },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useSecretSettings(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.master_key_storage).toBe("file");
  });

  test("surfaces error on API failure", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "settings fetch failed" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useSecretSettings(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("settings fetch failed");
  });
});

describe("useUpdateSecretSettings", () => {
  beforeEach(() => vi.clearAllMocks());

  test("calls PUT /settings/secrets with the correct body", async () => {
    const putMock = vi
      .fn()
      .mockResolvedValue({ data: { master_key_storage: "keychain" }, error: undefined });
    getApiClientMock.mockReturnValue({
      PUT: putMock,
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateSecretSettings(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ master_key_storage: "keychain" });
    });

    expect(putMock).toHaveBeenCalledWith(
      "/settings/secrets",
      expect.objectContaining({ body: { master_key_storage: "keychain" } }),
    );
  });

  test("invalidates the secret-settings query key on success", async () => {
    const putMock = vi
      .fn()
      .mockResolvedValue({ data: { master_key_storage: "file" }, error: undefined });
    getApiClientMock.mockReturnValue({
      PUT: putMock,
    } as unknown as ReturnType<typeof getApiClient>);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateSecretSettings(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ master_key_storage: "file" });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["settings", "secrets"] }),
    );
  });
});
