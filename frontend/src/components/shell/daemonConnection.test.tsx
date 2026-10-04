// src/components/shell/daemonConnection.test.tsx — the shell's connection phase: reconnecting, then offline, then back.
//
// Board 1.2.20 "Daemon connection": retries at 1, 2, 4, 8s; the page stays
// under the reconnecting bar for the first 10s of failures, then the offline
// state takes over; on recovery every query refetches and the shell is told.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { resetDaemonConnection, useDaemonConnectionDriver } from "./daemonConnection";
import { useDaemonState } from "@/components/settings/daemon/useDaemonState";

const status = vi.hoisted(() => ({
  current: { isError: false, error: null as unknown, errorUpdatedAt: 0, dataUpdatedAt: 0 } as {
    isError: boolean;
    error: unknown;
    errorUpdatedAt: number;
    dataUpdatedAt: number;
    data?: { status: string; port: number; version: string };
  },
  refetch: vi.fn(),
}));
vi.mock("@/lib/hooks/useDaemon", () => ({
  useDaemonStatus: () => ({ ...status.current, refetch: status.refetch }),
  useDaemonOutOfDate: () => ({ data: false }),
}));

function Probe({ onRecovered }: { onRecovered: () => void }) {
  const { connection } = useDaemonConnectionDriver(onRecovered);
  const state = useDaemonState();
  return (
    <>
      <div data-testid="phase">{connection.phase}</div>
      <div data-testid="attempt">{connection.attempt}</div>
      <div data-testid="daemon-state">{state.kind}</div>
    </>
  );
}

let qc: QueryClient;
function renderProbe(onRecovered = vi.fn()) {
  qc = new QueryClient();
  const utils = render(
    <QueryClientProvider client={qc}>
      <Probe onRecovered={onRecovered} />
    </QueryClientProvider>,
  );
  const rerender = () =>
    utils.rerender(
      <QueryClientProvider client={qc}>
        <Probe onRecovered={onRecovered} />
      </QueryClientProvider>,
    );
  return { rerender, onRecovered };
}

const RUNNING = { status: "ready", port: 38470, version: "1.0.0" };

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
});
afterEach(() => {
  vi.useRealTimers();
});

function fail(at: number) {
  status.current = {
    ...status.current,
    isError: true,
    error: new Error("down"),
    errorUpdatedAt: at,
  };
}

describe("useDaemonConnectionDriver", () => {
  test("a lost daemon reads reconnecting, retries with backoff, then reads offline after 10s", () => {
    const { rerender } = renderProbe();
    expect(screen.getByTestId("phase")).toHaveTextContent("ok");
    expect(screen.getByTestId("daemon-state")).toHaveTextContent("running");

    fail(1);
    rerender();
    expect(screen.getByTestId("phase")).toHaveTextContent("reconnecting");
    expect(screen.getByTestId("daemon-state")).toHaveTextContent("reconnecting");
    expect(screen.getByTestId("attempt")).toHaveTextContent("1");

    act(() => void vi.advanceTimersByTime(1000));
    expect(status.refetch).toHaveBeenCalledTimes(1);
    fail(2);
    rerender();
    expect(screen.getByTestId("attempt")).toHaveTextContent("2");

    act(() => void vi.advanceTimersByTime(9000));
    expect(screen.getByTestId("phase")).toHaveTextContent("offline");
    expect(screen.getByTestId("daemon-state")).toHaveTextContent("offline");
  });

  test("when the daemon answers again every query refetches and the shell is told once", () => {
    const { rerender, onRecovered } = renderProbe();
    fail(1);
    rerender();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    status.current = {
      isError: false,
      error: null,
      errorUpdatedAt: 1,
      dataUpdatedAt: 5,
      data: RUNNING,
    };
    rerender();
    expect(screen.getByTestId("phase")).toHaveTextContent("ok");
    expect(invalidate).toHaveBeenCalledWith();
    expect(onRecovered).toHaveBeenCalledOnce();
  });

  test("with no driver mounted a failing probe reads offline", () => {
    function StateOnly() {
      return <div data-testid="daemon-state">{useDaemonState().kind}</div>;
    }
    fail(1);
    render(<StateOnly />);
    expect(screen.getByTestId("daemon-state")).toHaveTextContent("offline");
  });
});
