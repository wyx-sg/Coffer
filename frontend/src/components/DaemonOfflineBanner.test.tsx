import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";
import { acceptance } from "@/test/acceptance";

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
  applyDaemonConnection: vi.fn(),
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
  test("brings its own card and not its own fixed slot", () => {
    // `FloatingBanners` owns the slot, and it is shared with
    // SyncAttentionBanner. While both owned an identical `fixed inset-x-0
    // top-4` wrapper they were drawn at the same coordinates, and a daemon
    // that is merely OUT OF DATE answers the sync status perfectly well — so
    // the pair really can be up at once.
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("ECONNREFUSED"),
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    const { container } = render(wrap(<DaemonOfflineBanner />));
    expect(container.querySelector(".fixed")).toBeNull();
    expect(screen.getByTestId("daemon-banner")).toBeInTheDocument();
  });

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

  acceptance(
    "desktop-app",
    "a restart hands back the connection it waited for",
    async () => {
      vi.resetModules();
      // The shell waited for the replacement to answer, so what it returns is
      // a working connection — and installing that, rather than asking for one
      // again, is what keeps a restart to a single daemon.
      const connection = { baseUrl: "http://127.0.0.1:8000/api/v1", token: "fresh-token" };
      const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true, ...connection });
      const applyMock = vi.fn();
      const connectMock = vi.fn();
      vi.doMock("@/lib/tauri", () => ({
        isTauri: () => true,
        restartDaemon: restartDaemonMock,
        applyDaemonConnection: applyMock,
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

      await waitFor(() => expect(applyMock).toHaveBeenCalledWith(expect.objectContaining(connection)));
      // A second handshake here arrived before the new daemon had bound a
      // port, and the handshake answers "no daemon running" by spawning one —
      // one click, two daemons.
      expect(connectMock).not.toHaveBeenCalled();
      // EVERY cached query carries responses fetched with the revoked token,
      // not just daemon/status — the whole cache refetches.
      await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith());
      // Order matters: refetching before the new credentials are installed would
      // 401 the whole cache and leave the app looking broken after a good restart.
      expect(applyMock.mock.invocationCallOrder[0]).toBeLessThan(
        invalidateSpy.mock.invocationCallOrder[0],
      );
    },
  );

  test("a replacement that never answers is reported as a failed restart", async () => {
    vi.resetModules();
    // The shell waits for the daemon it spawned; when that wait runs out there
    // is no connection to hand back and the restart itself has failed. There is
    // no half-success to word differently any more.
    const restartDaemonMock = vi
      .fn()
      .mockRejectedValue(
        new Error("coffer-daemon (pid 123) was started but did not answer within 90s"),
      );
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
      applyDaemonConnection: vi.fn(),
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

    expect(await screen.findByText(/did not answer within/)).toBeInTheDocument();
  });
});
