// A page of a switched-off experimental feature (spec experimental-features
// "Close every surface of a switched-off feature"): the route renders a notice
// that links to Settings → General, and the page itself never mounts.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

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
        <FeatureGate feature="knowledge">
          <p>the knowledge page</p>
        </FeatureGate>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => getMock.mockReset());

describe("FeatureGate", () => {
  test("a switched-off feature's page shows a notice linking to Settings → General", async () => {
    status({ knowledge: false, memory: true, vault_sync: true });
    renderGate();

    expect(await screen.findByText("Knowledge is switched off")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings → general/i })).toHaveAttribute(
      "href",
      "/settings/general",
    );
    expect(screen.queryByText("the knowledge page")).not.toBeInTheDocument();
  });

  test("a switched-on feature's page renders", async () => {
    status({ knowledge: true, memory: true, vault_sync: true });
    renderGate();

    expect(await screen.findByText("the knowledge page")).toBeInTheDocument();
  });

  test("a daemon that predates the gates serves everything", async () => {
    status(undefined);
    renderGate();

    expect(await screen.findByText("the knowledge page")).toBeInTheDocument();
  });

  test("nothing is claimed before the daemon answers", async () => {
    let answer: (value: unknown) => void = () => {};
    getMock.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderGate();

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("the knowledge page")).not.toBeInTheDocument();
    expect(screen.queryByText(/switched off/)).not.toBeInTheDocument();

    answer({ data: { status: "ready", features: { knowledge: true } } });
    expect(await screen.findByText("the knowledge page")).toBeInTheDocument();
  });
});
