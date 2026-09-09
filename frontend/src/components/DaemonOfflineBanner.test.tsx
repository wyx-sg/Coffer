import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DaemonOfflineBanner } from "./DaemonOfflineBanner";

vi.mock("@/lib/hooks/useDaemon", () => ({
  useDaemonStatus: vi.fn(),
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
      data: { version: "0.1.1" },
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

  test("shows a Retry button plus a terminal restart hint", () => {
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

  test("Retry refetches in place — it does NOT hard-reload the page", async () => {
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
