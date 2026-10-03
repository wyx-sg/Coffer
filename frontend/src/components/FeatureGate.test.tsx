// A page of a switched-off experimental feature (spec experimental-features
// "Make a switched-off feature look absent in the UI"): the route renders the
// app's not-found page — no notice that the feature is off and no switch-on
// button. The page itself never mounts until the feature is on, and nothing is
// claimed while the daemon has not answered. The gate here guards `knowledge`;
// the route-table tests prove every feature's pages sit behind their gate.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, matchRoutes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";

import { isValidElement } from "react";

import { appRoutes } from "@/router";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { FeatureGate } from "./FeatureGate";

const getMock = vi.fn();
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: getMock }),
  resetApiClient: vi.fn(),
}));

function daemon(features: Record<string, boolean>) {
  getMock.mockResolvedValue({
    data: {
      status: "ready",
      version: "0.0.0",
      executable: "/x",
      started_at: "2026-01-01T00:00:00Z",
      port: 1,
      features,
    },
  });
}

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <FeatureGate feature="knowledge" notFound={<p>the not-found page</p>}>
          <p>the fake page</p>
        </FeatureGate>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

describe("FeatureGate", () => {
  acceptance("experimental-features", "a switched-off feature's page is not found", async () => {
    daemon({ knowledge: false, models: true });
    renderGate();

    expect(await screen.findByText("the not-found page")).toBeInTheDocument();
    expect(screen.queryByText("the fake page")).not.toBeInTheDocument();
    expect(screen.queryByText(/switched off/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /switch on|open settings/i })).toBeNull();
  });

  test("a switched-on feature's page renders", async () => {
    daemon({ knowledge: true, models: false });
    renderGate();

    expect(await screen.findByText("the fake page")).toBeInTheDocument();
    expect(screen.queryByText("the not-found page")).not.toBeInTheDocument();
  });

  test("nothing is claimed before the daemon answers", async () => {
    let answer: (value: unknown) => void = () => {};
    getMock.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderGate();

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("the fake page")).not.toBeInTheDocument();
    expect(screen.queryByText("the not-found page")).not.toBeInTheDocument();

    answer({ data: { status: "ready", features: { knowledge: true } } });
    expect(await screen.findByText("the fake page")).toBeInTheDocument();
  });
});

// Every page of a feature is behind its gate, through the `feature` the
// sidebar entry carries: a deep link lands on the not-found page, not on the page.
describe("the route table", () => {
  const GATED: Record<string, string[]> = {
    models: ["/model-providers", "/model-providers/abc", "/model-providers/usage"],
    knowledge: ["/knowledge", "/knowledge/abc/history"],
    memory: ["/memory", "/memory/abc/delivered"],
    sync: ["/sync", "/sync/conflicts", "/sync/deletions"],
  };

  acceptance("web-ui", "a switched-off feature's address is not found", () => {
    for (const paths of Object.values(GATED)) {
      for (const path of paths) {
        const matches = matchRoutes(appRoutes, path) ?? [];
        const element = matches[matches.length - 1]?.route.element;
        const props = (element as { props: { notFound: { type: unknown } } }).props;
        expect(props.notFound.type, path).toBe(NotFoundPage);
      }
    }
  });

  for (const [feature, paths] of Object.entries(GATED)) {
    test(`every ${feature} page is wrapped in its gate`, () => {
      for (const path of paths) {
        const matches = matchRoutes(appRoutes, path) ?? [];
        const element = matches[matches.length - 1]?.route.element;
        expect(isValidElement(element) && element.type === FeatureGate, path).toBe(true);
        const props = (element as { props: { feature: string; notFound: { type: unknown } } })
          .props;
        expect(props.feature).toBe(feature);
        // A switched-off feature's page is the app's standard not-found page.
        expect(props.notFound.type).toBe(NotFoundPage);
      }
    });
  }

  test("an always-on page is not gated", () => {
    for (const path of [
      "/agents",
      "/skills",
      "/mcp-servers",
      "/secrets",
      "/activity",
      "/conversations",
      "/channels",
      "/",
    ]) {
      const matches = matchRoutes(appRoutes, path) ?? [];
      const element = matches[matches.length - 1]?.route.element;
      expect(isValidElement(element) && element.type === FeatureGate, path).toBe(false);
    }
  });
});
