// frontend/src/pages/settings/SettingsModal.test.tsx
//
// Settings as a modal over the page underneath, addressed by route, through
// the app's real route table (change revise-web-ui-ia; spec web-ui "Open
// Settings as a modal from the sidebar footer", "Organise Settings into five
// tabs"). Plain tests until the change is archived (its task 7.14b).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigate, useRoutes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { routes } from "@/router";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");

beforeEach(() => {
  const get = vi.fn().mockImplementation(() =>
    Promise.resolve({
      data: {
        resources: [],
        agents: [],
        candidates: [],
        entries: [],
        items: [],
        status: "ready",
        version: "0.0.0",
        port: 8000,
        started_at: "2026-01-01T00:00:00Z",
        features: {},
      },
      error: undefined,
    }),
  );
  vi.mocked(getApiClient).mockReturnValue({
    GET: get,
    PUT: get,
    POST: get,
  } as unknown as ReturnType<typeof getApiClient>);
});

const where = { pathname: "" };
let goBack: () => void = () => {};

function Probe() {
  where.pathname = useLocation().pathname;
  const navigate = useNavigate();
  goBack = () => navigate(-1);
  return null;
}

function AppRoutes() {
  return useRoutes(routes);
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openFromRow() {
  fireEvent.click(await screen.findByTestId("sidebar-settings"));
  return screen.findByTestId("settings-modal", {}, { timeout: 5_000 });
}

describe("the Settings modal", () => {
  // revise-web-ui-ia: web-ui "settings layout uses the redesigned tabbed sidebar"
  acceptance("web-ui", "settings layout uses the redesigned tabbed sidebar", async () => {
    renderAt("/settings");
    const modal = await screen.findByTestId("settings-modal", {}, { timeout: 5_000 });
    await waitFor(() => expect(where.pathname).toBe("/settings/general"));
    const tabs = within(within(modal).getByRole("navigation", { name: "Settings sections" }))
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(tabs).toEqual(["General", "Security", "Data", "Daemon", "About"]);
    expect(within(modal).getByRole("link", { name: "General" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    fireEvent.click(within(modal).getByRole("link", { name: "About" }));
    await waitFor(() => expect(where.pathname).toBe("/settings/about"));
    expect(
      await screen.findByTestId("settings-pane-about", {}, { timeout: 5_000 }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("settings-modal")).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "the Settings row opens Settings over the current page"
  test("the Settings row opens General over the current page", async () => {
    renderAt("/mcp-servers");
    expect(
      await screen.findByRole("heading", { level: 1, name: "MCP servers" }, { timeout: 5_000 }),
    ).toBeInTheDocument();
    await openFromRow();
    expect(where.pathname).toBe("/settings/general");
    // The page underneath is still rendered.
    expect(
      screen.getByRole("heading", { level: 1, name: "MCP servers", hidden: true }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-settings")).toHaveAttribute("aria-pressed", "true");
  });

  // revise-web-ui-ia: web-ui "closing Settings returns to the page underneath"
  test("Escape and Back both close it onto the page underneath", async () => {
    renderAt("/activity");
    await openFromRow();
    fireEvent.click(
      within(screen.getByTestId("settings-modal")).getByRole("link", { name: "Data" }),
    );
    await waitFor(() => expect(where.pathname).toBe("/settings/data"));

    fireEvent.keyDown(screen.getByTestId("settings-modal"), { key: "Escape" });
    await waitFor(() => expect(where.pathname).toBe("/activity"));
    expect(screen.queryByTestId("settings-modal")).not.toBeInTheDocument();

    await openFromRow();
    goBack();
    await waitFor(() => expect(where.pathname).toBe("/activity"));
    await waitFor(() => expect(screen.queryByTestId("settings-modal")).not.toBeInTheDocument());
  });

  // revise-web-ui-ia: web-ui "a deep link opens a Settings tab"
  test("a fresh load of a Settings tab opens it over Overview and closes to /", async () => {
    renderAt("/settings/daemon");
    const modal = await screen.findByTestId("settings-modal", {}, { timeout: 5_000 });
    expect(within(modal).getByRole("link", { name: "Daemon" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      await screen.findByTestId("settings-daemon-status", {}, { timeout: 5_000 }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Overview", hidden: true }),
    ).toBeInTheDocument();

    fireEvent.click(within(modal).getByRole("button", { name: "Close settings" }));
    await waitFor(() => expect(where.pathname).toBe("/"));
    expect(screen.queryByTestId("settings-modal")).not.toBeInTheDocument();
  });

  test("the General tab holds Coffer's model and no Experimental features card", async () => {
    renderAt("/settings/general");
    const pane = await screen.findByTestId("settings-pane-general", {}, { timeout: 5_000 });
    expect(within(pane).queryByText(/experimental features/i)).not.toBeInTheDocument();
    // Start at login moved to the Daemon tab.
    expect(within(pane).queryByText(/start at login/i)).not.toBeInTheDocument();
  });
});
