import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";

vi.mock("@/lib/hooks/useDaemon", () => ({
  useDaemonStatus: vi.fn(),
}));

vi.mock("@/lib/tauri", () => ({
  isTauri: () => false,
  restartDaemon: vi.fn(),
}));

const { useDaemonStatus } = await import("@/lib/hooks/useDaemon");
const useDaemonStatusMock = vi.mocked(useDaemonStatus);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe("DaemonOfflineBanner", () => {
  test("renders nothing when daemon is healthy", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: false,
      error: null,
    } as never);
    const { container } = render(wrap(<DaemonOfflineBanner />));
    expect(container.firstChild).toBeNull();
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

  test("in browser mode the recovery affordance is Reload, not a raw CLI command", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("nope"),
    } as never);
    render(wrap(<DaemonOfflineBanner />));
    // The `coffer daemon start` snippet was removed — the Reload control is
    // the only recovery affordance now.
    expect(screen.queryByText("coffer daemon start")).not.toBeInTheDocument();
    expect(screen.getByTestId("daemon-banner-reload")).toBeInTheDocument();
  });

  test("shows the Reload button in browser mode and clicking it calls window.location.reload", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("Failed to fetch"),
    } as never);

    // Stub window.location.reload so we can assert it was called.
    const reloadSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload: reloadSpy },
    });

    render(wrap(<DaemonOfflineBanner />));

    const reloadBtn = screen.getByTestId("daemon-banner-reload");
    expect(reloadBtn).toBeInTheDocument();
    expect(reloadBtn).toHaveTextContent("Reload");

    fireEvent.click(reloadBtn);
    expect(reloadSpy).toHaveBeenCalledOnce();
  });
});

// Separate describe-block isolates the desktop-mode (isTauri=true) branch
// so the lib/tauri mock can be re-installed without leaking into the other
// tests above.
describe("DaemonOfflineBanner (Tauri restart branch)", () => {
  test("renders a Restart button that invokes restartDaemon when clicked", async () => {
    vi.resetModules();
    const restartDaemonMock = vi.fn().mockResolvedValue({ pid: 123, started: true });
    vi.doMock("@/lib/tauri", () => ({
      isTauri: () => true,
      restartDaemon: restartDaemonMock,
    }));
    vi.doMock("@/lib/hooks/useDaemon", () => ({
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
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
    }));
    vi.doMock("@/lib/hooks/useDaemon", () => ({
      useDaemonStatus: () => ({ isError: true, error: new Error("offline") }),
    }));

    const { DaemonOfflineBanner: ReloadedBanner } = await import("./DaemonOfflineBanner");
    render(wrap(<ReloadedBanner />));

    const restartBtn = screen.getByRole("button", { name: /restart/i });
    fireEvent.click(restartBtn);
    // The rejection propagates through restartDaemon().catch(), which
    // writes restartError to state and renders the error text.
    expect(await screen.findByText(/permission denied/)).toBeInTheDocument();
  });
});
