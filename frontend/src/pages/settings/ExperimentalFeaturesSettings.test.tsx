// The Features tab of Settings (in every build), and the sidebar it drives
// (spec experimental-features "Show the Features tab in every build").
//
// The thing worth pinning is that one switch is one request and the sidebar
// follows it in the same session: the tab and the rail read two different
// routes (`/daemon/features` and `/daemon/status`), and a tab that moved while
// the rail waited for its next 30-second poll would say a feature is on that
// the user cannot find. The four features are the real registry: `knowledge`
// owns Knowledge, `memory` Memory, `sync` Sync, `models` Model providers and
// Usage.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarNav } from "@/components/SidebarNav";
import { acceptance } from "@/test/acceptance";
import { ExperimentalFeaturesSettings } from "./ExperimentalFeaturesSettings";

const getMock = vi.fn();
const putMock = vi.fn();
const deleteMock = vi.fn();
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: getMock, PUT: putMock, DELETE: deleteMock }),
  resetApiClient: vi.fn(),
}));
// The sync attention dot has its own tests; here it would only add a request.
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: () => ({ data: undefined, isError: false }),
}));

type Source = "pin" | "setting" | "default";
type State = Record<string, { enabled: boolean; source: Source }>;

const ALL_OFF: State = {
  knowledge: { enabled: false, source: "default" },
  memory: { enabled: false, source: "default" },
  sync: { enabled: false, source: "default" },
  models: { enabled: false, source: "default" },
};

/** A fake daemon holding `state`: the status and the list both read it. */
function daemon(initial: State) {
  const state: State = structuredClone(initial);
  getMock.mockImplementation((path: string) => {
    if (path === "/daemon/status") {
      return Promise.resolve({
        data: {
          status: "ready",
          version: "0.0.0",
          executable: "/x",
          started_at: "2026-01-01T00:00:00Z",
          port: 1,
          features: Object.fromEntries(Object.entries(state).map(([k, v]) => [k, v.enabled])),
        },
      });
    }
    if (path === "/daemon/features") {
      return Promise.resolve({
        data: {
          features: Object.entries(state).map(([key, v]) => ({ key, ...v })),
        },
      });
    }
    return Promise.resolve({ data: undefined });
  });
  return state;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/settings/features"]}>
        <TooltipProvider>
          <SidebarNav collapsed={false} pathname="/" />
          <ExperimentalFeaturesSettings />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// An experimental entry's name carries its marker after the label.
const sidebarLink = (name: string) =>
  within(screen.getByRole("navigation")).queryByRole("link", { name: new RegExp(`^${name}\\b`) });

beforeEach(() => {
  getMock.mockReset();
  putMock.mockReset();
  deleteMock.mockReset();
});

describe("ExperimentalFeaturesSettings", () => {
  acceptance("experimental-features", "the features tab switches a feature", async () => {
    const state = daemon(ALL_OFF);
    putMock.mockImplementation(
      (_path: string, init: { params: { path: { key: string } }; body: { enabled: boolean } }) => {
        const key = init.params.path.key;
        state[key] = { enabled: init.body.enabled, source: "setting" };
        return Promise.resolve({ data: { key, ...state[key] } });
      },
    );
    renderPage();

    const toggle = await screen.findByRole("switch", { name: "Knowledge" });
    expect(toggle).not.toBeChecked();
    await waitFor(() => expect(sidebarLink("Secrets")).toBeInTheDocument());
    expect(sidebarLink("Knowledge")).toBeNull();

    fireEvent.click(toggle);

    await waitFor(() => expect(sidebarLink("Knowledge")).toBeInTheDocument());
    expect(putMock).toHaveBeenCalledTimes(1);
    expect(putMock).toHaveBeenCalledWith("/daemon/features/{key}", {
      params: { path: { key: "knowledge" } },
      body: { enabled: true },
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: "Knowledge" })).toBeChecked());
    expect(
      within(screen.getByTestId("feature-knowledge")).getByText(/On, set on this machine/),
    ).toBeInTheDocument();
    // The others were not touched.
    expect(sidebarLink("Memory")).toBeNull();
    expect(sidebarLink("Model providers")).toBeNull();
    expect(sidebarLink("Sync")).toBeNull();
  });

  acceptance("experimental-features", "settings carry the Features tab", async () => {
    daemon({
      knowledge: { enabled: true, source: "setting" },
      memory: { enabled: false, source: "pin" },
      sync: { enabled: false, source: "default" },
      models: { enabled: true, source: "pin" },
    });
    renderPage();

    const knowledge = await screen.findByTestId("feature-knowledge");
    expect(within(knowledge).getByText("Experimental")).toBeInTheDocument();
    expect(within(knowledge).getByText(/On, set on this machine/)).toBeInTheDocument();
    expect(within(knowledge).getByRole("switch", { name: "Knowledge" })).toBeChecked();
    expect(within(knowledge).getByText(/Notes and documents/)).toBeInTheDocument();
    expect(
      within(screen.getByTestId("feature-memory")).getByText(/Pinned by COFFER_FEATURES/),
    ).toBeInTheDocument();
    const sync = screen.getByTestId("feature-sync");
    expect(within(sync).getByText(/Off by default/)).toBeInTheDocument();
    expect(within(sync).getByText("Experimental")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("feature-models")).getByText("Experimental"),
    ).toBeInTheDocument();
    // Registry order, and nothing about phases or channels.
    const rows = screen.getAllByTestId(/^feature-/).map((row) => row.getAttribute("data-testid"));
    expect(rows).toEqual(["feature-knowledge", "feature-memory", "feature-sync", "feature-models"]);
    for (const row of screen.getAllByTestId(/^feature-/)) {
      expect(row.textContent).not.toMatch(/phase|channel/i);
    }
  });

  acceptance("experimental-features", "a pinned feature's switch is disabled", async () => {
    daemon({ ...ALL_OFF, models: { enabled: false, source: "pin" } });
    renderPage();

    expect(await screen.findByRole("switch", { name: "Model providers" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Sync" })).toBeEnabled();
  });

  test("a failed write puts the switch back and shows the error beside it", async () => {
    daemon({ ...ALL_OFF, sync: { enabled: true, source: "setting" } });
    putMock.mockResolvedValue({
      error: {
        error: { code: "FEATURE_PINNED", message: "pinned", details: { feature: "sync" } },
      },
    });
    renderPage();

    const toggle = await screen.findByRole("switch", { name: "Sync" });
    await waitFor(() => expect(toggle).toBeChecked());
    fireEvent.click(toggle);

    const row = screen.getByTestId("feature-sync");
    expect(await within(row).findByRole("alert")).toHaveTextContent(/pinned by COFFER_FEATURES/i);
    expect(screen.getByRole("switch", { name: "Sync" })).toBeChecked();
    expect(sidebarLink("Sync")).toBeInTheDocument();
  });

  test("Reset to default removes this machine's setting, only where one exists", async () => {
    const state = daemon({
      ...ALL_OFF,
      memory: { enabled: true, source: "setting" },
    });
    deleteMock.mockImplementation((_path: string, init: { params: { path: { key: string } } }) => {
      const key = init.params.path.key;
      state[key] = { enabled: false, source: "default" };
      return Promise.resolve({ data: { key, ...state[key] } });
    });
    renderPage();

    const row = await screen.findByTestId("feature-memory");
    expect(within(screen.getByTestId("feature-sync")).queryByRole("button")).toBeNull();
    fireEvent.click(await within(row).findByRole("button", { name: "Reset to default" }));

    await waitFor(() => expect(deleteMock).toHaveBeenCalledTimes(1));
    expect(deleteMock).toHaveBeenCalledWith("/daemon/features/{key}", {
      params: { path: { key: "memory" } },
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: "Memory" })).not.toBeChecked());
    expect(within(row).queryByRole("button", { name: "Reset to default" })).toBeNull();
    expect(within(row).getByText(/Off by default/)).toBeInTheDocument();
  });
});
