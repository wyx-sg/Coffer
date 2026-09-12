// frontend/src/lib/hooks/useDaemonSettings.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { DAEMON_SETTINGS_KEY, useDaemonSettings, useUpdateDaemonPort } from "./useDaemonSettings";

vi.mock("@/lib/api/daemonSettings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/daemonSettings")>();
  return { ...actual, daemonSettingsApi: { get: vi.fn(), setPort: vi.fn() } };
});
const { daemonSettingsApi } = await import("@/lib/api/daemonSettings");
const getMock = vi.mocked(daemonSettingsApi.get);
const setPortMock = vi.mocked(daemonSettingsApi.setPort);

const AUTOMATIC = { configured_port: null, effective_port: 8003, restart_required: false };

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

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("useDaemonSettings", () => {
  test("returns the daemon's port settings", async () => {
    getMock.mockResolvedValue({ ...AUTOMATIC, configured_port: 8123, restart_required: true });

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDaemonSettings(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toMatchObject({ configured_port: 8123, restart_required: true });
  });

  test("surfaces a failure rather than a blank card", async () => {
    getMock.mockRejectedValue(new Error("daemon settings fetch failed"));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDaemonSettings(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("daemon settings fetch failed");
  });
});

describe("useUpdateDaemonPort", () => {
  test("sends the port and invalidates the settings query", async () => {
    setPortMock.mockResolvedValue({ ...AUTOMATIC, configured_port: 8123, restart_required: true });

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useUpdateDaemonPort(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(8123);
    });

    expect(setPortMock).toHaveBeenCalledWith(8123);
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: DAEMON_SETTINGS_KEY }),
    );
  });

  test("null hands the choice back to the daemon's free-port scan", async () => {
    setPortMock.mockResolvedValue(AUTOMATIC);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateDaemonPort(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(null);
    });

    expect(setPortMock).toHaveBeenCalledWith(null);
  });
});
