import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

  test("surfaces the terminal restart command and no Retry button", () => {
    useDaemonStatusMock.mockReturnValue({
      isError: true,
      error: new Error("nope"),
    } as never);
    render(wrap(<DaemonOfflineBanner />));
    // The browser cannot restart the daemon, so the only affordance is the
    // command that does; the 30s status poll clears the banner by itself.
    expect(screen.getByText("coffer daemon start")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
