import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { DaemonOfflineState, DaemonStatusBar } from "./DaemonOfflineBanner";
import type { DaemonConnection } from "./shell/daemonConnection";
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
  inDesktopShell: () => false,
  restartDaemon: vi.fn(),
  applyDaemonConnection: vi.fn(),
  connectToShellDaemon: vi.fn(),
}));

const { useDaemonStatus, useDaemonOutOfDate } = await import("@/lib/hooks/useDaemon");
const useDaemonStatusMock = vi.mocked(useDaemonStatus);
const useDaemonOutOfDateMock = vi.mocked(useDaemonOutOfDate);

const OFFLINE: DaemonConnection = {
  phase: "offline",
  attempt: 5,
  nextRetryAt: null,
  lastReplyAt: null,
  starting: false,
  driven: true,
};
const RECONNECTING: DaemonConnection = {
  ...OFFLINE,
  phase: "reconnecting",
  attempt: 3,
  nextRetryAt: Date.now() + 4000,
  lastReplyAt: Date.now() - 5000,
};

/** The offline state as Layout mounts it once the reconnect grace has run out. */
function DaemonOfflineBanner({ onRetry = () => {} }: { onRetry?: () => void }) {
  return <DaemonOfflineState connection={OFFLINE} onRetry={onRetry} />;
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DaemonOfflineBanner", () => {
  test("is drawn in line in the workspace, not in a fixed slot over the app", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("ECONNREFUSED"),
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    const { container } = render(wrap(<DaemonOfflineBanner />));
    expect(container.querySelector(".fixed")).toBeNull();
    expect(screen.getByTestId("daemon-banner")).toBeInTheDocument();
  });

  test("while reconnecting a bar counts the attempts and Retry now probes again", () => {
    useDaemonStatusMock.mockReturnValue({ isError: true, error: new Error("down") } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    const retry = vi.fn();
    render(wrap(<DaemonStatusBar connection={RECONNECTING} onRetry={retry} />));
    const bar = screen.getByTestId("daemon-reconnecting");
    expect(bar).toHaveTextContent("Reconnecting to the daemon…");
    expect(bar).toHaveTextContent(
      /Attempt 3 · next try in \ds · changes are paused, nothing is lost/,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry now" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  test("the offline state's Retry probes again", () => {
    useDaemonStatusMock.mockReturnValue({ isError: true, error: new Error("down") } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    const retry = vi.fn();
    render(wrap(<DaemonOfflineBanner onRetry={retry} />));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  test("renders nothing when daemon is healthy", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: false,
      error: null,
      data: { version: "0.1.1" },
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    const { container } = render(
      wrap(<DaemonStatusBar connection={{ ...OFFLINE, phase: "ok" }} onRetry={() => {}} />),
    );
    expect(container.firstChild).toBeNull();
  });

  test("shows the banner when the status query errors", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("ECONNREFUSED"),
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    render(wrap(<DaemonOfflineBanner />));
    expect(screen.getByText("Coffer’s daemon isn’t running")).toBeInTheDocument();
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
    render(wrap(<DaemonStatusBar connection={{ ...OFFLINE, phase: "ok" }} onRetry={() => {}} />));
    expect(screen.getByText(/out of date/i)).toBeInTheDocument();
    expect(screen.getByTestId("daemon-banner")).toHaveAttribute(
      "data-banner-code",
      "DAEMON_OUT_OF_DATE",
    );
  });

  test("in a browser it surfaces the terminal restart command and no start button", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("nope"),
    } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    render(wrap(<DaemonOfflineBanner />));
    // The browser cannot start the daemon, so the recovery is the command
    // that does; Retry only probes again, and the retries clear the state.
    expect(screen.getByText("Or start it from a terminal")).toBeInTheDocument();
    expect(screen.getByText("coffer daemon start")).toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Retry",
      "Copy",
      "Copy",
    ]);
  });

  acceptance("web-ui", "the offline screen offers the daemon log command in a browser", () => {
    useDaemonStatusMock.mockReturnValue({ isError: true, error: new Error("down") } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    render(wrap(<DaemonOfflineBanner />));
    expect(screen.getByRole("heading", { level: 1 })).toHaveClass("font-bold");
    expect(screen.getByText("Read the daemon log from a terminal")).toBeInTheDocument();
    expect(screen.getByText("coffer log daemon")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open daemon log" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open daemon log" })).toBeNull();
  });

  test("the reconnecting bar shows a still ring, not a spinner", () => {
    useDaemonStatusMock.mockReturnValue({ isError: true, error: new Error("down") } as never);
    useDaemonOutOfDateMock.mockReturnValue({ data: false } as never);
    render(wrap(<DaemonStatusBar connection={RECONNECTING} onRetry={() => {}} />));
    const ring = screen.getByTestId("daemon-reconnecting").querySelector("svg");
    expect(ring).not.toBeNull();
    expect(ring!.getAttribute("class")).not.toMatch(/animate-spin/);
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
      inDesktopShell: () => true,
      restartDaemon: restartDaemonMock,
      connectToShellDaemon: vi.fn().mockResolvedValue(undefined),
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineState: Reloaded } = await import("./DaemonOfflineBanner");
    const ReloadedBanner = () => <Reloaded connection={OFFLINE} onRetry={() => {}} />;
    render(wrap(<ReloadedBanner />));

    const restartBtn = screen.getByTestId("daemon-banner-restart");
    fireEvent.click(restartBtn);
    await waitFor(() => expect(restartDaemonMock).toHaveBeenCalledOnce());
  });

  acceptance("web-ui", "the offline screen opens the daemon log without the daemon", async () => {
    vi.resetModules();
    const shellInvokeMock = vi.fn().mockResolvedValue(undefined);
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      inDesktopShell: () => true,
      shellInvoke: shellInvokeMock,
      restartDaemon: vi.fn(),
      connectToShellDaemon: vi.fn(),
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineState: Reloaded } = await import("./DaemonOfflineBanner");
    render(wrap(<Reloaded connection={OFFLINE} onRetry={() => {}} />));

    fireEvent.click(screen.getByRole("button", { name: "Open daemon log" }));
    await waitFor(() => expect(shellInvokeMock).toHaveBeenCalledWith("show_daemon_log"));
    expect(screen.queryByText("coffer log daemon")).toBeNull();
  });

  test("surfaces a restart error message when the Tauri command throws", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockRejectedValue(new Error("permission denied"));
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      inDesktopShell: () => true,
      restartDaemon: restartDaemonMock,
      connectToShellDaemon: vi.fn(),
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineState: Reloaded } = await import("./DaemonOfflineBanner");
    const ReloadedBanner = () => <Reloaded connection={OFFLINE} onRetry={() => {}} />;
    render(wrap(<ReloadedBanner />));

    fireEvent.click(screen.getByTestId("daemon-banner-restart"));
    expect(await screen.findByText(/permission denied/)).toBeInTheDocument();
  });

  acceptance("desktop-app", "a restart hands back the connection it waited for", async () => {
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
      inDesktopShell: () => true,
      restartDaemon: restartDaemonMock,
      applyDaemonConnection: applyMock,
      connectToShellDaemon: connectMock,
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineState: Reloaded } = await import("./DaemonOfflineBanner");
    const ReloadedBanner = () => <Reloaded connection={OFFLINE} onRetry={() => {}} />;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ReloadedBanner />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByTestId("daemon-banner-restart"));

    await waitFor(() =>
      expect(applyMock).toHaveBeenCalledWith(expect.objectContaining(connection)),
    );
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
  });

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
      inDesktopShell: () => true,
      restartDaemon: restartDaemonMock,
      applyDaemonConnection: vi.fn(),
      connectToShellDaemon: vi.fn(),
    }));
    vi.doMock("@/lib/hooks/useDaemon", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
      useDaemonOutOfDate: () => ({ data: false }),
    }));

    const { DaemonOfflineState: Reloaded } = await import("./DaemonOfflineBanner");
    const ReloadedBanner = () => <Reloaded connection={OFFLINE} onRetry={() => {}} />;
    render(wrap(<ReloadedBanner />));

    fireEvent.click(screen.getByTestId("daemon-banner-restart"));

    expect(await screen.findByText(/did not answer within/)).toBeInTheDocument();
  });
});
