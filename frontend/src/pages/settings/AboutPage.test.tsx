// frontend/src/pages/settings/AboutPage.test.tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
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
  channel: "stable",
  status: "ready",
  started_at: "2026-05-01T08:00:00Z",
  port: 8000,
  executable: "/Applications/Coffer.app/Contents/MacOS/coffer-daemon",
  machine_id: "m-1",
  machine_name: "work-mac",
  features: { knowledge: true, memory: false, sync: true },
  upstream_summary: null,
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

  // The requirement behind this marker is removed by change revise-web-ui-ia
  // (the daemon now shows on Settings → Daemon); the marker goes at archive.
  // About itself still names no daemon on screen.
  acceptance("web-ui", "settings shows no daemon tab and no daemon status", async () => {
    mockStatus();
    const { container } = render(<AboutPage />, { wrapper: wrap });

    await waitFor(() => {
      expect(screen.getByText("Version 0.7.42 · stable channel")).toBeInTheDocument();
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
    expect(screen.getByText(/reading the version/i)).toBeInTheDocument();
  });

  // web-ui "copy diagnostics carries no secret" (change revise-web-ui-ia; the
  // acceptance marker is added when the change is archived and the scenario
  // reaches openspec/specs).
  test("copy diagnostics carries no secret", async () => {
    mockStatus();
    const injected = window as unknown as { __COFFER_TOKEN__?: string };
    injected.__COFFER_TOKEN__ = "tok-must-not-leak";
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<AboutPage />, { wrapper: wrap });
    await screen.findByText("Version 0.7.42 · stable channel");

    fireEvent.click(screen.getByRole("button", { name: /copy diagnostics/i }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const text = writeText.mock.calls[0][0] as string;
    expect(text).toContain("Coffer: 0.7.42");
    expect(text).toContain("Channel: stable");
    expect(text).toMatch(/Host: browser/);
    expect(text).toContain("Daemon: running on port 8000");
    expect(text).toContain("Features: knowledge, sync");
    expect(text).not.toContain("tok-must-not-leak");
    expect(text).not.toMatch(/token|secret/i);
    delete injected.__COFFER_TOKEN__;
  });
});
