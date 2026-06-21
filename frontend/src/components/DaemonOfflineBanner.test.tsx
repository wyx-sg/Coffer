import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";

vi.mock("@/lib/hooks/useDaemon", () => ({
  useDaemonStatus: vi.fn(),
  useDaemonOutOfDate: vi.fn(() => ({ data: false })),
}));

vi.mock("@/lib/tauri", () => ({
  isTauri: () => false,
  restartDaemon: vi.fn(),
  getDaemonInfo: vi.fn(),
}));

const { useDaemonStatus, useDaemonOutOfDate } = await import("@/lib/hooks/useDaemon");
const useDaemonStatusMock = vi.mocked(useDaemonStatus);
const useDaemonOutOfDateMock = vi.mocked(useDaemonOutOfDate);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("DaemonOfflineBanner", () => {
  test("renders nothing when daemon is healthy", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: false,
      error: null,
      data: { version: "0.1.1" },
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    const { container } = render(wrap(<DaemonOfflineBanner />));
    expect(container.firstChild).toBeNull();
  });

  test("surfaces an out-of-date banner when the daemon version is stale, even though it is reachable", () => {
    // Daemon responds fine (no query error) but reports an older version than
    // the app expects — a stale detached daemon the new app reused (P2).
    useDaemonStatusMock.mockReturnValue({
      isError: false,
      error: null,
      data: { version: "0.1.0" },
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: true } as never);
    render(wrap(<DaemonOfflineBanner />));
    expect(screen.getByText(/out of date/i)).toBeInTheDocument();
    // It reuses the recovery affordance (Reload in browser mode) rather than
    // a separate auto-kill path.
    expect(screen.getByTestId("daemon-banner-reload")).toBeInTheDocument();
  });

  test("shows the banner when the status query errors", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("ECONNREFUSED"),
    } as never);
    render(wrap(<DaemonOfflineBanner />));
    expect(screen.getByText(/Daemon offline/i)).toBeInTheDocument();
    expect(screen.getByText(/ECONNREFUSED/)).toBeInTheDocument();
  });

  test("in browser mode shows a Retry button plus a terminal restart hint", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("nope"),
    } as never);
    render(wrap(<DaemonOfflineBanner />));
    // Retry (soft re-check) is the in-app affordance; the browser can't restart
    // the daemon, so the actual recovery command is surfaced as a hint.
    expect(screen.getByTestId("daemon-banner-reload")).toBeInTheDocument();
    expect(screen.getByText("coffer daemon start")).toBeInTheDocument();
  });

  test("in browser mode Retry refetches in place — it does NOT hard-reload the page", async () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("Failed to fetch"),
    } as never);

    // A hard window.location.reload() would navigate to the page host and blank
    // the app if that host (Vite dev server / daemon-served bundle) is itself
    // down. Assert we DON'T call it, and instead refetch in place.
    const reloadSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload: reloadSpy },
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries").mockResolvedValue();
    render(
      <QueryClientProvider client={qc}>
        <DaemonOfflineBanner />
      </QueryClientProvider>,
    );

    const retryBtn = screen.getByTestId("daemon-banner-reload");
    expect(retryBtn).toHaveTextContent("Retry");

    fireEvent.click(retryBtn);
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith());
    expect(reloadSpy).not.toHaveBeenCalled();
  });
});

// Separate describe-block isolates the desktop-mode (isTauri=true) branch
// so the lib/tauri mock can be re-installed without leaking into the other
// tests above.
describe("DaemonOfflineBanner (Tauri restart branch)", () => {
  afterEach(() => {
    // The recovery flow writes the Tauri-injected globals; clean them so
    // they can't leak auth state into other tests.
    const w = window as unknown as Record<string, unknown>;
    delete w.__COFFER_BASE_URL__;
    delete w.__COFFER_TOKEN__;
  });

  test("renders a Restart button that invokes restartDaemon when clicked", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true });
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      getDaemonInfo: vi
        .fn()
        .mockResolvedValue({ baseUrl: "http://127.0.0.1:9001/api/v1", token: "tok" }),
    }));
    vi.doMock("@/lib/hooks/useDaemon", () => ({
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    const restartBtn = screen.getByRole("button", { name: /restart/i });
    expect(restartBtn).toBeInTheDocument();

    fireEvent.click(restartBtn);
    // The mocked promise resolves immediately, but the click handler is
    // async — flush microtasks via the resolved value of the mock.
    await restartDaemonMock.mock.results[0]?.value;
    expect(restartDaemonMock).toHaveBeenCalledOnce();
  });

  test("surfaces a restart error message when the Tauri command throws", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockRejectedValue(new Error("permission denied"));
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      getDaemonInfo: vi.fn(),
    }));
    vi.doMock("@/lib/hooks/useDaemon", () => ({
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    const restartBtn = screen.getByRole("button", { name: /restart/i });
    fireEvent.click(restartBtn);
    // The rejection propagates through restartDaemon().catch(), which
    // writes restartError to state and renders the error text.
    expect(await screen.findByText(/permission denied/)).toBeInTheDocument();
  });

  test("a successful restart re-fetches daemon info, swaps the token, resets the API client, and refetches all queries", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true });
    // The daemon mints a NEW token on every start — the recovery flow must
    // pick it up, or every request 401s until the app is relaunched (P0-5).
    const getDaemonInfoMock = vi
      .fn()
      .mockResolvedValue({ baseUrl: "http://127.0.0.1:9042/api/v1", token: "fresh-token" });
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      getDaemonInfo: getDaemonInfoMock,
    }));
    vi.doMock("@/lib/hooks/useDaemon", () => ({
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    // Same module registry as the component under test, so getApiClient()
    // identity tells us whether the memoised client was really dropped.
    const clientMod = await import("@/lib/api/client");
    const staleClient = clientMod.getApiClient();

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    render(<QueryClientProvider client={qc}>{<ReloadedBanner />}</QueryClientProvider>);

    fireEvent.click(screen.getByRole("button", { name: /restart/i }));

    const w = window as unknown as Record<string, unknown>;
    await waitFor(() => expect(w.__COFFER_TOKEN__).toBe("fresh-token"));
    expect(w.__COFFER_BASE_URL__).toBe("http://127.0.0.1:9042/api/v1");
    expect(getDaemonInfoMock).toHaveBeenCalledOnce();
    // The memoised client captured the old base URL — it must be rebuilt.
    expect(clientMod.getApiClient()).not.toBe(staleClient);
    // EVERY cached query carries responses fetched with the revoked token,
    // not just daemon/status — the whole cache refetches.
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith());
  });

  test("when the daemon restarts but reconnecting fails, a distinct reconnect error is shown and the stale auth is untouched", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true });
    const getDaemonInfoMock = vi
      .fn()
      .mockRejectedValue(new Error("coffer-daemon did not become ready within 15s"));
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      getDaemonInfo: getDaemonInfoMock,
    }));
    vi.doMock("@/lib/hooks/useDaemon", () => ({
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    fireEvent.click(screen.getByRole("button", { name: /restart/i }));

    // Distinct copy from a plain restart failure: the daemon DID restart,
    // but the app could not fetch its new credentials.
    expect(await screen.findByText(/restarted, but/i)).toBeInTheDocument();
    expect(screen.getByText(/did not become ready/)).toBeInTheDocument();
    // The injected globals stay untouched on the failure path.
    const w = window as unknown as Record<string, unknown>;
    expect(w.__COFFER_TOKEN__).toBeUndefined();
  });
});
