// The Experimental features card on Settings → General, and the sidebar it
// drives (spec experimental-features "List and switch the features on the
// General tab").
//
// The thing worth pinning is that one switch is one request and the sidebar
// follows it in the same session: the card and the rail read two different
// routes (`/daemon/features` and `/daemon/status`), and a card that moved
// while the rail waited for its next 30-second poll would say a feature is on
// that the user cannot find.
//
// No real feature is registered (every one so far has graduated), so the
// daemon here registers test-only ones — `fake_alpha`, `fake_beta`,
// `fake_gamma` — and the sidebar carries one test-only entry for each.
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
vi.mock("@/lib/navigation", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/navigation")>();
  const { FlaskConical } = await import("lucide-react");
  const groups = [
    ...real.NAV_GROUPS,
    {
      labelKey: "Fake group",
      entries: [
        { to: "/alpha", labelKey: "Alpha", icon: FlaskConical, feature: "fake_alpha" },
        { to: "/beta", labelKey: "Beta", icon: FlaskConical, feature: "fake_beta" },
        { to: "/gamma", labelKey: "Gamma", icon: FlaskConical, feature: "fake_gamma" },
      ],
    },
  ];
  return { ...real, NAV_GROUPS: groups, NAV_ENTRIES: groups.flatMap((g) => g.entries) };
});
vi.mock("@/lib/api/client", () => ({
  getApiClient: () => ({ GET: getMock, PUT: putMock }),
  resetApiClient: vi.fn(),
}));
// The sync attention dot has its own tests; here it would only add a request.
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: () => ({ data: undefined, isError: false }),
}));

type Source = "pin" | "setting" | "channel";
type State = Record<string, { enabled: boolean; source: Source }>;

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
          channel: "stable",
          features: Object.fromEntries(Object.entries(state).map(([k, v]) => [k, v.enabled])),
        },
      });
    }
    if (path === "/daemon/features") {
      return Promise.resolve({
        data: {
          channel: "stable",
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
      <MemoryRouter initialEntries={["/settings/general"]}>
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
});

describe("ExperimentalFeaturesSettings", () => {
  acceptance("experimental-features", "the general tab switches a feature", async () => {
    const state = daemon({
      fake_alpha: { enabled: false, source: "channel" },
      fake_beta: { enabled: false, source: "channel" },
      fake_gamma: { enabled: false, source: "channel" },
    });
    putMock.mockImplementation(
      (_path: string, init: { params: { path: { key: string } }; body: { enabled: boolean } }) => {
        const key = init.params.path.key;
        state[key] = { enabled: init.body.enabled, source: "setting" };
        return Promise.resolve({ data: { key, ...state[key] } });
      },
    );
    renderPage();

    const toggle = await screen.findByRole("switch", { name: "fake_beta" });
    expect(toggle).not.toBeChecked();
    expect(sidebarLink("Beta")).toBeNull();

    fireEvent.click(toggle);

    await waitFor(() => expect(sidebarLink("Beta")).toBeInTheDocument());
    expect(putMock).toHaveBeenCalledTimes(1);
    expect(putMock).toHaveBeenCalledWith("/daemon/features/{key}", {
      params: { path: { key: "fake_beta" } },
      body: { enabled: true },
    });
    await waitFor(() => expect(screen.getByRole("switch", { name: "fake_beta" })).toBeChecked());
    expect(
      within(screen.getByTestId("feature-fake_beta")).getByText("Set on this machine"),
    ).toBeInTheDocument();
    // The others were not touched.
    expect(sidebarLink("Gamma")).toBeNull();
    expect(sidebarLink("Alpha")).toBeNull();
  });

  test("lists every feature with its state and the layer that decided it", async () => {
    daemon({
      fake_alpha: { enabled: true, source: "setting" },
      fake_beta: { enabled: false, source: "pin" },
      fake_gamma: { enabled: false, source: "channel" },
    });
    renderPage();

    const alpha = await screen.findByTestId("feature-fake_alpha");
    expect(within(alpha).getByText("On")).toBeInTheDocument();
    expect(within(alpha).getByText("Set on this machine")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("feature-fake_beta")).getByText(/Pinned by COFFER_FEATURES/),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("feature-fake_gamma")).getByText("Default for the stable channel"),
    ).toBeInTheDocument();
  });

  test("a pinned feature's switch is disabled", async () => {
    daemon({
      fake_alpha: { enabled: true, source: "channel" },
      fake_beta: { enabled: false, source: "pin" },
      fake_gamma: { enabled: true, source: "channel" },
    });
    renderPage();

    expect(await screen.findByRole("switch", { name: "fake_beta" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "fake_gamma" })).toBeEnabled();
  });

  test("a failed write puts the switch back and shows the error beside it", async () => {
    daemon({
      fake_alpha: { enabled: true, source: "channel" },
      fake_beta: { enabled: false, source: "channel" },
      fake_gamma: { enabled: true, source: "channel" },
    });
    putMock.mockResolvedValue({
      error: {
        error: { code: "FEATURE_PINNED", message: "pinned", details: { feature: "fake_gamma" } },
      },
    });
    renderPage();

    const toggle = await screen.findByRole("switch", { name: "fake_gamma" });
    await waitFor(() => expect(toggle).toBeChecked());
    fireEvent.click(toggle);

    const row = screen.getByTestId("feature-fake_gamma");
    expect(await within(row).findByRole("alert")).toHaveTextContent(/pinned by COFFER_FEATURES/i);
    expect(screen.getByRole("switch", { name: "fake_gamma" })).toBeChecked();
    expect(sidebarLink("Gamma")).toBeInTheDocument();
  });

  acceptance(
    "experimental-features",
    "the general tab shows nothing while no feature is registered",
    async () => {
      daemon({});
      const { container } = renderPage();

      await waitFor(() => expect(getMock).toHaveBeenCalledWith("/daemon/features"));
      await new Promise((r) => setTimeout(r, 0));
      expect(screen.queryByText("Experimental features")).not.toBeInTheDocument();
      expect(container.querySelector("[data-testid^='feature-']")).toBeNull();
    },
  );
});
