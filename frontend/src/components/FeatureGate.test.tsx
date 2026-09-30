// A page of a switched-off experimental feature (spec experimental-features
// "Close every surface of a switched-off feature"): the route renders a notice
// that says so, with a Switch on button (the same write as Settings → General)
// and a way to open Settings; a pinned feature explains the pin instead. The
// page itself never mounts until the feature is on. No real feature is
// registered, so the gate guards a test-only `fake_feature`, which has no
// translated name and so is named by its key.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";

import { FeatureGate } from "./FeatureGate";

const getMock = vi.fn();
const putMock = vi.fn();
vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({ GET: getMock, PUT: putMock }),
  resetApiClient: vi.fn(),
}));

type Source = "pin" | "setting" | "channel";

function daemon(features: Record<string, boolean> | undefined, source: Source = "channel") {
  // Replaced, never mutated: the query cache holds the object it was handed.
  let state: Record<string, boolean> = { ...features };
  getMock.mockImplementation(async (path: string) => {
    if (path === "/daemon/features") {
      return {
        data: {
          channel: "stable",
          features: Object.entries(state).map(([key, enabled]) => ({ key, enabled, source })),
        },
      };
    }
    return {
      data: {
        status: "ready",
        version: "0.0.0",
        executable: "/x",
        started_at: "2026-01-01T00:00:00Z",
        port: 1,
        channel: "stable",
        features: features === undefined ? undefined : state,
      },
    };
  });
  putMock.mockImplementation(async (_path: string, init: { params: { path: { key: string } } }) => {
    state = { ...state, [init.params.path.key]: true };
    return { data: { key: init.params.path.key, enabled: true, source: "setting" } };
  });
}

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FeatureGate feature="fake_feature">
          <p>the fake page</p>
        </FeatureGate>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset();
  putMock.mockReset();
});

describe("FeatureGate", () => {
  acceptance(
    "experimental-features",
    "a switched-off feature's page says it is switched off",
    async () => {
      daemon({ fake_feature: false, other_feature: true });
      renderGate();

      expect(await screen.findByText("fake_feature is switched off")).toBeInTheDocument();
      expect(screen.queryByText(/coffer config set/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Open Settings" })).toBeInTheDocument();
      expect(screen.queryByText("the fake page")).not.toBeInTheDocument();
    },
  );

  acceptance(
    "experimental-features",
    "a switched-off feature's page switches it on in place",
    async () => {
      daemon({ fake_feature: false });
      renderGate();

      const button = await screen.findByRole("button", { name: "Switch on" });
      await waitFor(() => expect(button).toBeEnabled());
      fireEvent.click(button);
      await waitFor(() => expect(putMock).toHaveBeenCalled());

      expect(await screen.findByText("the fake page")).toBeInTheDocument();
      expect(putMock).toHaveBeenCalledTimes(1);
      expect(putMock.mock.calls[0][1]).toMatchObject({
        params: { path: { key: "fake_feature" } },
        body: { enabled: true },
      });
    },
  );

  acceptance(
    "experimental-features",
    "a pinned feature's page explains the pin instead of switching",
    async () => {
      daemon({ fake_feature: false }, "pin");
      renderGate();

      expect(await screen.findByText(/held off by COFFER_FEATURES/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Switch on" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Open Settings" })).toBeInTheDocument();
    },
  );

  test("a switched-on feature's page renders", async () => {
    daemon({ fake_feature: true, other_feature: true });
    renderGate();

    expect(await screen.findByText("the fake page")).toBeInTheDocument();
  });

  test("a daemon that predates the gates serves everything", async () => {
    daemon(undefined);
    renderGate();

    expect(await screen.findByText("the fake page")).toBeInTheDocument();
  });

  test("nothing is claimed before the daemon answers", async () => {
    let answer: (value: unknown) => void = () => {};
    getMock.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderGate();

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("the fake page")).not.toBeInTheDocument();
    expect(screen.queryByText(/switched off/)).not.toBeInTheDocument();

    answer({ data: { status: "ready", features: { fake_feature: true } } });
    expect(await screen.findByText("the fake page")).toBeInTheDocument();
  });
});
