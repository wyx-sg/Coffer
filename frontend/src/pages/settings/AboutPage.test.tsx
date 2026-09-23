// frontend/src/pages/settings/AboutPage.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const STATUS = {
  version: "0.7.42",
  status: "ready",
  started_at: "2026-05-01T08:00:00Z",
  port: 8000,
};

function mockStatus() {
  getApiClientMock.mockReturnValue({
    GET: vi.fn().mockResolvedValue({ data: STATUS, error: undefined }),
  } as unknown as ReturnType<typeof getApiClient>);
}

describe("AboutPage", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  test("shows license and source unconditionally", () => {
    // useDaemonStatus is allowed to be in-flight; the other fields don't depend on it.
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})), // pending forever
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    expect(screen.getByText("MIT")).toBeInTheDocument();
    expect(screen.getByText(/github\.com\/wyx-sg\/Coffer/)).toBeInTheDocument();
  });

  test("shows version, license and source only — no daemon port or start time", async () => {
    mockStatus();
    const { container } = render(<AboutPage />, { wrapper: wrap });

    await waitFor(() => {
      expect(screen.getByText("0.7.42")).toBeInTheDocument();
    });
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("License")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    // A user never needs to know Coffer runs a background daemon.
    expect(container.textContent).not.toMatch(/daemon/i);
    expect(screen.queryByText("8000")).not.toBeInTheDocument();
  });

  test("falls back to '—' for the version before /daemon/status resolves", () => {
    getApiClientMock.mockReturnValue({
      GET: vi.fn().mockReturnValue(new Promise(() => {})),
    } as unknown as ReturnType<typeof getApiClient>);
    render(<AboutPage />, { wrapper: wrap });

    expect(screen.getAllByText("—")).toHaveLength(1);
  });

  test("Copy diagnostics puts every row on the clipboard as label: value lines", async () => {
    mockStatus();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<AboutPage />, { wrapper: wrap });
    await screen.findByText("0.7.42");

    fireEvent.click(screen.getByRole("button", { name: /copy diagnostics/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const text = writeText.mock.calls[0][0] as string;
    expect(text).toContain("Version: 0.7.42");
    expect(text).toContain("License: MIT");
    expect(text).not.toMatch(/daemon/i);
    expect(text).toContain("Source: https://github.com/wyx-sg/Coffer");
  });
});
