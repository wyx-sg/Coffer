// frontend/src/pages/settings/AboutPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { AboutPage } from "./AboutPage";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("AboutPage", () => {
  beforeEach(() => vi.clearAllMocks());

  test("shows license and source unconditionally", () => {
    // useDaemonStatus is allowed to be in-flight; the other fields don't depend on it.
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})), // pending forever
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    expect(screen.getByText("MIT")).toBeInTheDocument();
    expect(screen.getByText(/github\.com\/wyx-sg\/Coffer/)).toBeInTheDocument();
  });

  test("shows the version returned by /daemon/status", async () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockResolvedValue({
        data: {
          version: "0.7.42",
          status: "running",
          uptime_seconds: 0,
          listen_address: "127.0.0.1:1717",
        },
        error: undefined,
      }),
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    await waitFor(() => {
      expect(screen.getByText("0.7.42")).toBeInTheDocument();
    });
  });

  test("falls back to '—' before /daemon/status resolves", () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})),
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
