// A page of a switched-off experimental feature (spec experimental-features
// "Close every surface of a switched-off feature"): the route renders a notice
// that says so (linking to no Settings tab), and the page itself never mounts.
// No real feature is registered, so the gate guards a test-only `fake_feature`,
// which has no translated name and so is named by its key.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";

import { FeatureGate } from "./FeatureGate";

const getMock = vi.fn();
vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({ GET: getMock }),
  resetApiClient: vi.fn(),
}));

function status(features: Record<string, boolean> | undefined) {
  getMock.mockResolvedValue({
    data: {
      status: "ready",
      version: "0.0.0",
      executable: "/x",
      started_at: "2026-01-01T00:00:00Z",
      port: 1,
      channel: "stable",
      features,
    },
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

beforeEach(() => getMock.mockReset());

describe("FeatureGate", () => {
  acceptance(
    "experimental-features",
    "a switched-off feature's page says it is switched off",
    async () => {
      status({ fake_feature: false, other_feature: true });
      renderGate();

      expect(await screen.findByText("fake_feature is switched off")).toBeInTheDocument();
      expect(screen.getByText(/coffer config set feature\.fake_feature on/)).toBeInTheDocument();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.queryByText("the fake page")).not.toBeInTheDocument();
    },
  );

  test("a switched-on feature's page renders", async () => {
    status({ fake_feature: true, other_feature: true });
    renderGate();

    expect(await screen.findByText("the fake page")).toBeInTheDocument();
  });

  test("a daemon that predates the gates serves everything", async () => {
    status(undefined);
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
