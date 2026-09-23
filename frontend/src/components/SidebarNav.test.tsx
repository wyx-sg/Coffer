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
import { MemoryRouter, matchRoutes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarNav } from "./SidebarNav";
import { routes } from "@/router";

// The Sync entry carries an attention dot, which asks the daemon for the
// vault's last round. Stub it; the dot's own rules live in
// `lib/hooks/useSyncAttention`.
const syncStatus = vi.fn(() => ({ data: undefined, isError: false }));
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: () => syncStatus(),
}));

afterEach(() => {
  syncStatus.mockReturnValue({ data: undefined, isError: false });
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
  const resolved = hrefs.map((href) => leafRoute(href));
  // Each entry is its own list route — the path itself, never the catch-all.
  resolved.forEach((route, i) => {
    expect(route).not.toBe("*");
    expect(`/${route}`).toBe(hrefs[i]);
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

// --- the attention dot (spec vault-sync FR-096) ---------------------------
//
// It replaced a banner that floated over whatever page the user was on. The
// dot has to keep the property that mattered — a vault nobody is looking at
// still gets noticed — without the one that did not: arguing on every page
// until the underlying state changes.

const HELD = {
  status: "awaiting_confirmation",
  conflicts: [],
  error: null,
  pending: { direction: "publish", breaches: [] },
};

describe("the Sync attention dot", () => {
  test("is absent while the vault is converging", () => {
    syncStatus.mockReturnValue({
      data: { last_run: { status: "ok", conflicts: [], error: null, pending: null } },
      isError: false,
    } as never);
    const { queryByTestId } = renderNav();
    expect(queryByTestId("nav-dot-sync")).toBeNull();
  });

  test("appears when the last round needs answering", async () => {
    syncStatus.mockReturnValue({ data: { last_run: HELD }, isError: false } as never);
    const { findByTestId } = renderNav();
    expect(await findByTestId("nav-dot-sync")).toBeInTheDocument();
  });

  acceptance("vault-sync", "a held vault says so where the user already is", async () => {
    syncStatus.mockReturnValue({ data: { last_run: HELD }, isError: false } as never);
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
    syncStatus.mockReturnValue({ data: { last_run: HELD }, isError: true } as never);
    const { queryByTestId } = renderNav();
    expect(queryByTestId("nav-dot-sync")).toBeNull();
  });

  test("survives a collapsed rail, where the label is gone", async () => {
    syncStatus.mockReturnValue({ data: { last_run: HELD }, isError: false } as never);
    const { findByTestId } = renderNav("/", true);
    expect(await findByTestId("nav-dot-sync")).toBeInTheDocument();
  });
});
