// frontend/src/lib/hooks/useFsBrowse.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useFsBrowse } from "./useFsBrowse";

vi.mock("@/lib/api/fs", () => ({ fsApi: { browse: vi.fn() } }));
const { fsApi } = await import("@/lib/api/fs");
const browseMock = vi.mocked(fsApi.browse);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

afterEach(() => vi.clearAllMocks());

describe("useFsBrowse", () => {
  test("lists the directory the daemon reports for the given path", async () => {
    browseMock.mockResolvedValue({ path: "/home/u", parent: "/home", entries: [] });
    const { result } = renderHook(() => useFsBrowse("/home/u"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(browseMock).toHaveBeenCalledWith("/home/u");
    expect(result.current.data?.path).toBe("/home/u");
  });

  test("passes null through as 'home' and stays idle while disabled", () => {
    const { result } = renderHook(() => useFsBrowse(null, { enabled: false }), {
      wrapper: wrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(browseMock).not.toHaveBeenCalled();
  });
});
