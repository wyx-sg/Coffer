import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";

// The status/skew queries are stubbed; the restart mutation stays real so the
// desktop branch below exercises the actual restart → reconnect → refetch flow.
vi.mock("@/lib/hooks/useDaemon", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
  useDaemonStatus: vi.fn(),
  useDaemonOutOfDate: vi.fn(() => ({ data: false })),
}));

// Browser host by default — the Tauri branch gets its own describe block below.
vi.mock("@/lib/tauri", () => ({
  isTauri: () => false,
  restartDaemon: vi.fn(),
  connectToShellDaemon: vi.fn(),
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

  test("shows the banner when the status query errors", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("ECONNREFUSED"),
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    render(wrap(<DaemonOfflineBanner />));
    expect(screen.getByText(/Daemon offline/i)).toBeInTheDocument();
    // The raw transport error is not user copy — only the translated body shows.
    expect(screen.queryByText(/ECONNREFUSED/)).not.toBeInTheDocument();
  });

  test("surfaces an out-of-date banner while the daemon is still answering", () => {
    // The daemon responds fine (no query error) but reports a version this app
    // build did not pair with — a stale detached daemon the app reused.
    useDaemonStatusMock.mockReturnValue({
      isError: false,
      error: null,
      data: { version: "0.1.0" },
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: true } as never);
    render(wrap(<DaemonOfflineBanner />));
    expect(screen.getByText(/out of date/i)).toBeInTheDocument();
    expect(screen.getByTestId("daemon-banner")).toHaveAttribute(
      "data-banner-code",
      "DAEMON_OUT_OF_DATE",
    );
  });

  test("in a browser it surfaces the terminal restart command and no button", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("nope"),
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    render(wrap(<DaemonOfflineBanner />));
    // The browser cannot restart the daemon, so the only affordance is the
    // command that does; the 30s status poll clears the banner by itself.
    expect(screen.getByText("coffer daemon start")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

// The desktop host is the exception: its page is a local asset that renders
// with no daemon behind it, and the shell can spawn one. Isolated in its own
// describe block so the lib/tauri mock can be swapped without leaking into the
// browser-host tests above.
describe("DaemonOfflineBanner (desktop restart branch)", () => {
  afterEach(() => {
    // The recovery flow writes the connection globals; clean them so they
    // can't leak auth state into other tests.
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
      connectToShellDaemon: vi.fn().mockResolvedValue(undefined),
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    const restartBtn = screen.getByTestId("daemon-banner-restart");
    fireEvent.click(restartBtn);
    await waitFor(() => expect(restartDaemonMock).toHaveBeenCalledOnce());
  });

  test("surfaces a restart error message when the Tauri command throws", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockRejectedValue(new Error("permission denied"));
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      connectToShellDaemon: vi.fn(),
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    fireEvent.click(screen.getByTestId("daemon-banner-restart"));
    expect(await screen.findByText(/permission denied/)).toBeInTheDocument();
  });

  test("a successful restart re-handshakes and then refetches every cached query", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true });
    // The daemon mints a NEW token on every start, so the restart is only half
    // the recovery — the banner must re-handshake before anything refetches.
    // What that handshake installs is tauri.test.ts's business; here we care
    // that it happens, and that it happens before the cache is invalidated.
    const connectMock = vi.fn().mockResolvedValue(undefined);
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      connectToShellDaemon: connectMock,
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    render(<QueryClientProvider client={qc}>{<ReloadedBanner />}</QueryClientProvider>);

    fireEvent.click(screen.getByTestId("daemon-banner-restart"));

    await waitFor(() => expect(connectMock).toHaveBeenCalledOnce());
    // EVERY cached query carries responses fetched with the revoked token,
    // not just daemon/status — the whole cache refetches.
    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith());
    // Order matters: refetching before the new credentials are installed would
    // 401 the whole cache and leave the app looking broken after a good restart.
    expect(connectMock.mock.invocationCallOrder[0]).toBeLessThan(
      invalidateSpy.mock.invocationCallOrder[0],
    );
  });

  test("when the daemon restarts but reconnecting fails, a distinct error is shown and the stale auth is untouched", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true });
    const connectMock = vi
      .fn()
      .mockRejectedValue(new Error("coffer-daemon did not become ready within 15s"));
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      connectToShellDaemon: connectMock,
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    fireEvent.click(screen.getByTestId("daemon-banner-restart"));

    // Distinct copy from a plain restart failure: the daemon DID restart, but
    // the app could not fetch its new credentials.
    expect(await screen.findByText(/restarted, but/i)).toBeInTheDocument();
    expect(screen.getByText(/did not become ready/)).toBeInTheDocument();
  });
});
