// frontend/src/components/SidebarNav.test.tsx
// The sidebar's information architecture, which is a product decision and not
// a styling one: what is a vault RESOURCE and what is something you DO.
//
// Resources claims to list one entry per resource kind that has a list UI, so
// that claim is what this pins down — a kind that grows a surface and never
// reaches the rail is reachable only by typing its URL, and a row that outlives
// its feature leads to a 404.
import { afterEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { render, waitFor, within } from "@testing-library/react";
import { isValidElement } from "react";
import { MemoryRouter, Navigate, matchRoutes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarNav } from "./SidebarNav";
import { routes } from "@/router";

// The Sync entry carries an attention dot, which asks the daemon for the
// vault's last round. Stub it; the dot's own rules live in
// `lib/hooks/useSyncAttention`.
const syncStatus = vi.fn((enabled?: boolean) => {
  void enabled;
  return { data: undefined, isError: false };
});
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: (enabled?: boolean) => syncStatus(enabled),
}));

// Which experimental features the daemon reports on. Every one of them is on
// unless a test says otherwise — the eleven-entry assertions below are about a
// build with nothing switched off.
const ALL_ON = { vault_sync: true, knowledge: true, memory: true };
const features = vi.fn((): Record<string, boolean | undefined> => ALL_ON);
vi.mock("@/lib/hooks/useFeatures", () => ({
  useFeatureEnabled: (key: string) => features()[key],
}));

afterEach(() => {
  syncStatus.mockReset();
  syncStatus.mockReturnValue({ data: undefined, isError: false });
  features.mockReturnValue(ALL_ON);
  localStorage.clear();
});

function renderNav(at = "/", collapsed = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <TooltipProvider>
          <SidebarNav collapsed={collapsed} />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The rows of the group whose label is `label`, as `[name, href]` pairs.
 *  Found by the group-label class rather than by text: "Agents" is both a
 *  group heading and a row inside it. */
function group(label: string): [string, string | null][] {
  const heading = Array.from(document.querySelectorAll(".nav-group-label")).find(
    (node) => node.textContent === label,
  );
  const container = heading!.parentElement!;
  return within(container)
    .getAllByRole("link")
    .map((link) => [link.textContent ?? "", link.getAttribute("href")]);
}

describe("SidebarNav", () => {
  acceptance("web-ui", "resources holds one entry per kind with a list", () => {
    renderNav();

    expect(group("Resources").map(([name]) => name)).toEqual([
      "MCP servers",
      "Skills",
      "Knowledge",
      "Memory",
      "Model providers",
      "Channels",
    ]);
  });

  test("Agents holds what you DO with an agent, not vault assets", () => {
    renderNav();

    expect(group("Agents")).toEqual([
      ["Agents", "/agents"],
      ["Chat", "/chat"],
    ]);
  });
});

/** The leaf route a path resolves to in the app's real route table. */
function leafRoute(path: string): string | undefined {
  const matches = matchRoutes(routes, path) ?? [];
  return matches[matches.length - 1]?.route.path;
}

/** Whether the leaf route a path resolves to only redirects somewhere else. */
function isRedirect(path: string): boolean {
  const matches = matchRoutes(routes, path) ?? [];
  const element = matches[matches.length - 1]?.route.element;
  return isValidElement(element) && element.type === Navigate;
}

function groupLabels(): string[] {
  return Array.from(document.querySelectorAll(".nav-group-label")).map((n) => n.textContent ?? "");
}

acceptance("web-ui", "the sidebar groups agents, resources and system by role", () => {
  renderNav();

  expect(groupLabels()).toEqual(["Agents", "Resources", "System"]);
  expect(group("Agents").map(([name]) => name)).toEqual(["Agents", "Chat"]);
  expect(group("Resources").map(([, href]) => href)).not.toContain("/agents");
  expect(group("Resources").map(([name]) => name)).not.toContain("Agents");
  expect(group("System").map(([name]) => name)).toEqual(["Activity", "Sync", "Settings"]);
});

acceptance("web-ui", "every resource entry opens a list page of its own", () => {
  renderNav();

  const hrefs = group("Resources").map(([, href]) => href!);
  expect(hrefs).toHaveLength(6);
  // The check below can tell a redirect apart: the retired /resources is one.
  expect(isRedirect("/resources")).toBe(true);
  const resolved = hrefs.map((href) => leafRoute(href));
  // Each entry is its own list route — the path itself, never the catch-all.
  resolved.forEach((route, i) => {
    expect(route).not.toBe("*");
    expect(`/${route}`).toBe(hrefs[i]);
    // A route that only redirects is not a list page of its own.
    expect(isRedirect(hrefs[i])).toBe(false);
  });
  expect(new Set(resolved).size).toBe(hrefs.length);
});

acceptance("web-ui", "the sidebar carries no placeholder entries", () => {
  renderNav();

  const links = Array.from(document.querySelectorAll("nav a"));
  expect(links.length).toBe(11);
  for (const link of links) {
    const href = link.getAttribute("href");
    expect(href).toBeTruthy();
    expect(leafRoute(href!)).not.toBe("*");
    expect(link.textContent ?? "").not.toMatch(/soon|not yet|coming/i);
    expect(link).not.toHaveAttribute("aria-disabled", "true");
  }
  expect(document.body.textContent ?? "").not.toMatch(/coming soon|not yet implemented/i);
});

// --- the attention dot (spec vault-sync "Say a vault needs a human where the user
// already is") ---
//
// It replaced a banner that floated over whatever page the user was on. The
// dot has to keep the property that mattered — a vault nobody is looking at
// still gets noticed — without the one that did not: arguing on every page
// until the underlying state changes.

/** A configured remote that is switched on — a paused one never raises the dot. */
const ON = { enabled: true };

const HELD = {
  status: "awaiting_confirmation",
  conflicts: [],
  error: null,
  pending: { direction: "publish", breaches: [] },
};

describe("the Sync attention dot", () => {
  test("is absent while the vault is converging", () => {
    syncStatus.mockReturnValue({
      data: { remote: ON, last_run: { status: "ok", conflicts: [], error: null, pending: null } },
      isError: false,
    } as never);
    const { queryByTestId } = renderNav();
    expect(queryByTestId("nav-dot-sync")).toBeNull();
  });

  test("appears when the last round needs answering", async () => {
    syncStatus.mockReturnValue({ data: { remote: ON, last_run: HELD }, isError: false } as never);
    const { findByTestId } = renderNav();
    expect(await findByTestId("nav-dot-sync")).toBeInTheDocument();
  });

  acceptance("vault-sync", "a held vault says so where the user already is", async () => {
    syncStatus.mockReturnValue({ data: { remote: ON, last_run: HELD }, isError: false } as never);
    // On /sync the user is looking at the thing itself: no dot over their own
    // reading, and the situation is marked seen.
    const onPage = renderNav("/sync");
    expect(onPage.queryByTestId("nav-dot-sync")).toBeNull();
    await waitFor(() => expect(localStorage.getItem("coffer.sync.attentionSeen")).not.toBeNull());
    onPage.unmount();

    // Back on any other page, the same situation no longer asks.
    const elsewhere = renderNav("/agents");
    await waitFor(() => expect(elsewhere.queryByTestId("nav-dot-sync")).toBeNull());
  });

  test("a daemon that cannot answer raises no sync dot", () => {
    // That is the offline banner's job, and a stale cached round must not
    // outlive it into a second claim on the same screen.
    syncStatus.mockReturnValue({ data: { remote: ON, last_run: HELD }, isError: true } as never);
    const { queryByTestId } = renderNav();
    expect(queryByTestId("nav-dot-sync")).toBeNull();
  });

  test("survives a collapsed rail, where the label is gone", async () => {
    syncStatus.mockReturnValue({ data: { remote: ON, last_run: HELD }, isError: false } as never);
    const { findByTestId } = renderNav("/", true);
    expect(await findByTestId("nav-dot-sync")).toBeInTheDocument();
  });
});

// --- experimental features (spec experimental-features "Close every surface
// of a switched-off feature") ---

describe("a switched-off experimental feature", () => {
  acceptance("web-ui", "a switched-off feature leaves the sidebar", () => {
    features.mockReturnValue({ vault_sync: false, knowledge: false, memory: true });
    renderNav();

    expect(group("Agents").map(([name]) => name)).toEqual(["Agents", "Chat"]);
    expect(group("Resources").map(([name]) => name)).toEqual([
      "MCP servers",
      "Skills",
      "Memory",
      "Model providers",
      "Channels",
    ]);
    expect(group("System").map(([name]) => name)).toEqual(["Activity", "Settings"]);
  });

  test("an entry whose feature is not known yet is left out rather than flashed in", () => {
    features.mockReturnValue({});
    renderNav();

    const hrefs = Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href"));
    expect(hrefs).not.toContain("/knowledge");
    expect(hrefs).not.toContain("/memory");
    expect(hrefs).not.toContain("/sync");
    expect(hrefs).toHaveLength(8);
  });

  test("switched-off sync neither polls nor raises the attention dot", () => {
    features.mockReturnValue({ ...ALL_ON, vault_sync: false });
    syncStatus.mockReturnValue({ data: { remote: ON, last_run: HELD }, isError: false } as never);
    const { queryByTestId } = renderNav();

    expect(queryByTestId("nav-dot-sync")).toBeNull();
    expect(syncStatus).toHaveBeenCalled();
    for (const [enabled] of syncStatus.mock.calls) expect(enabled).toBe(false);
  });
});
