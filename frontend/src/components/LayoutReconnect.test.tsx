// src/components/LayoutReconnect.test.tsx — the shell keeps the page mounted while the daemon comes back within seconds.
//
// Spec web-ui "Show a self-clearing offline banner": for the first 10s of
// failures the page stays where it was, dimmed and inert, under the
// reconnecting bar; when the daemon answers again the bar goes, every query is
// read again and a toast says the app reconnected. The phase machine itself is
// shell/daemonConnection.test.tsx; this is the shell drawing it.
import { afterEach, beforeEach, expect, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { acceptance } from "@/test/acceptance";
import { Layout } from "./Layout";
import { resetDaemonConnection } from "./shell/daemonConnection";

const status = vi.hoisted(() => ({
  current: {} as {
    isError: boolean;
    error: unknown;
    errorUpdatedAt: number;
    dataUpdatedAt: number;
    data?: { status: string; port: number; version: string };
  },
  refetch: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemon", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useDaemon")>()),
  useDaemonStatus: () => ({ ...status.current, refetch: status.refetch }),
  useDaemonOutOfDate: () => ({ data: false }),
}));
// The rail's own parts are tested where they live.
vi.mock("./SidebarNav", () => ({ SidebarNav: () => null }));
vi.mock("./shell/SidebarFooter", () => ({ SidebarFooter: () => null }));
vi.mock("./secret/PendingApprovalsSheet", () => ({ PendingApprovalsSheet: () => null }));
vi.mock("./palette/CommandPalette", () => ({ CommandPalette: () => null }));

const RUNNING = { status: "ready", port: 8000, version: "1.0.0" };

/** A page with state of its own, so a remount would show as a reset count. */
function Page() {
  const [count, setCount] = useState(0);
  return (
    <button type="button" onClick={() => setCount((n) => n + 1)}>
      count {count}
    </button>
  );
}

const PAGES = [{ path: "*", element: <Page /> }];

let qc: QueryClient;
function tree() {
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/mcp-servers"]}>
          <Routes>
            <Route path="*" element={<Layout pageRoutes={PAGES} settingsRoutes={[]} />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  resetDaemonConnection();
  status.refetch.mockReset();
  status.current = {
    isError: false,
    error: null,
    errorUpdatedAt: 0,
    dataUpdatedAt: 1,
    data: RUNNING,
  };
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

acceptance("web-ui", "a daemon that comes back within seconds leaves the page in place", () => {
  const { rerender } = render(tree());
  fireEvent.click(screen.getByRole("button", { name: "count 0" }));
  const page = () => screen.getByRole("button", { name: /count/, hidden: true });
  // The frame the shell draws the page in.
  const frame = () => page().parentElement!;

  // The daemon stops answering: the page stays, dimmed and inert, under the bar.
  status.current = {
    ...status.current,
    isError: true,
    error: new Error("down"),
    errorUpdatedAt: 2,
  };
  rerender(tree());
  expect(screen.getByTestId("daemon-reconnecting")).toHaveTextContent(
    "Reconnecting to the daemon…",
  );
  expect(page()).toHaveTextContent("count 1");
  expect(frame()).toHaveAttribute("aria-busy", "true");
  expect(frame()).toHaveAttribute("inert");

  // The first retry runs after a second; the daemon still does not answer.
  act(() => void vi.advanceTimersByTime(1000));
  expect(status.refetch).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("daemon-reconnecting")).toBeInTheDocument();

  // It answers again within 10s: the bar goes, the same page is still there,
  // every query is read again and a toast says so.
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  status.current = {
    isError: false,
    error: null,
    errorUpdatedAt: 2,
    dataUpdatedAt: 5,
    data: RUNNING,
  };
  rerender(tree());
  expect(screen.queryByTestId("daemon-reconnecting")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "count 1" })).toBeInTheDocument();
  expect(frame()).not.toHaveAttribute("aria-busy");
  expect(frame()).not.toHaveAttribute("inert");
  expect(invalidate).toHaveBeenCalledWith();
  expect(screen.getByText("Reconnected")).toBeInTheDocument();
});
