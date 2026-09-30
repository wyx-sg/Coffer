// frontend/src/components/SidebarNav.test.tsx
// The sidebar's information architecture, which is a product decision and not
// a styling one: Overview, then five groups by what the user comes to do
// (ADR sidebar-grouped-by-what-the-person-comes-to-do).
//
// Several markers below still name the scenarios of the role-grouped sidebar
// the change revise-web-ui-ia replaces; they move to that change's scenario
// names (noted beside each) when it is archived (its task 7.1).
import { afterEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { render, waitFor, within } from "@testing-library/react";
import { isValidElement } from "react";
import { MemoryRouter, Navigate, matchRoutes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarNav } from "./SidebarNav";
import { appRoutes } from "@/router";

// The Sync entry carries an attention dot, which asks the daemon for the
// vault's last round. Stub it; the dot's own rules live in
// `lib/hooks/useSyncAttention`.
const syncStatus = vi.fn(() => ({ data: undefined, isError: false }));
vi.mock("@/lib/hooks/useSync", () => ({
  useSyncStatus: () => syncStatus(),
}));

// No real entry carries an experimental feature, so the tests of the feature
// gates add test-only ones: `/fake` in the System group, and a group of its own
// whose one entry is flagged. Both features are off unless a test says
// otherwise, so every other assertion here is about the real fifteen entries.
vi.mock("@/lib/navigation", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/navigation")>();
  const { FlaskConical } = await import("lucide-react");
  const groups = real.NAV_GROUPS.map((g) =>
    g.labelKey === "nav.group.system"
      ? {
          ...g,
          entries: [
            ...g.entries,
            { to: "/fake", labelKey: "Fake", icon: FlaskConical, feature: "fake_feature" },
          ],
        }
      : g,
  );
  groups.push({
    labelKey: "Fake group",
    entries: [
      { to: "/fake-group", labelKey: "Fake grouped", icon: FlaskConical, feature: "fake_group" },
    ],
  });
  return { ...real, NAV_GROUPS: groups, NAV_ENTRIES: groups.flatMap((g) => g.entries) };
});

const ALL_OFF = { fake_feature: false, fake_group: false };
const features = vi.fn((): Record<string, boolean> | null => ALL_OFF);
vi.mock("@/lib/hooks/useFeatures", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useFeatures")>()),
  useFeatureMap: () => features(),
}));

afterEach(() => {
  syncStatus.mockReset();
  syncStatus.mockReturnValue({ data: undefined, isError: false });
  features.mockReturnValue(ALL_OFF);
  localStorage.clear();
});

function renderNav(at = "/", collapsed = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <TooltipProvider>
          <SidebarNav collapsed={collapsed} pathname={at} />
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
    .map((link) => [entryName(link), link.getAttribute("href")]);
}

/** A row's name without the experimental marker some rows carry beside it. */
function entryName(link: HTMLElement): string {
  const marker = link.querySelector('[data-testid^="nav-experimental-"]');
  return (link.textContent ?? "").replace(marker?.textContent ?? "", "");
}

/** The entries under no heading — Overview. */
function ungrouped(): string[] {
  const nav = document.querySelector("nav")!;
  const first = nav.firstElementChild!;
  return within(first as HTMLElement)
    .getAllByRole("link")
    .map((link) => entryName(link));
}

describe("SidebarNav", () => {
  // revise-web-ui-ia: web-ui "each listed resource kind has one sidebar entry"
  acceptance("web-ui", "resources holds one entry per kind with a list", () => {
    renderNav();

    // Each listed resource kind has exactly one entry, filed by what the user
    // does with it; there is no Resources heading any more.
    expect(groupLabels()).not.toContain("Resources");
    const all = Array.from(document.querySelectorAll("nav a")).map((a) =>
      entryName(a as HTMLElement),
    );
    for (const name of [
      "MCP servers",
      "Custom tools",
      "Skills",
      "Knowledge",
      "Memory",
      "Model providers",
      "Channels",
    ]) {
      expect(all.filter((n) => n === name)).toHaveLength(1);
    }
    expect(group("Capabilities").map(([name]) => name)).toEqual(
      expect.arrayContaining(["MCP servers", "Custom tools", "Skills"]),
    );
    expect(group("Context").map(([name]) => name)).toEqual(["Knowledge", "Memory"]);
    expect(group("Agents").map(([name]) => name)).toContain("Model providers");
    expect(group("Run").map(([name]) => name)).toContain("Channels");
  });

  test("Overview sits above the groups, under no heading", () => {
    renderNav();

    expect(ungrouped()).toEqual(["Overview"]);
    expect(group("Agents")).toEqual([
      ["Agents", "/agents"],
      ["Model providers", "/model-providers"],
    ]);
  });

  test("the index marks Overview only, and a detail page marks its list's entry", () => {
    const home = renderNav("/");
    expect(home.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(home.getByRole("link", { name: "Agents" })).not.toHaveAttribute("aria-current");
    home.unmount();

    const detail = renderNav("/skills/release-notes/delivery");
    expect(detail.getByRole("link", { name: "Skills" })).toHaveAttribute("aria-current", "page");
    expect(detail.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  test("zh labels follow the glossary", async () => {
    const { default: i18n } = await import("@/i18n");
    await i18n.changeLanguage("zh");
    try {
      renderNav();
      expect(groupLabels()).toEqual(["智能体", "运行", "能力", "上下文", "系统"]);
      expect(ungrouped()).toEqual(["总览"]);
      expect(group("智能体").map(([name]) => name)).toEqual(["智能体", "模型提供商"]);
      expect(group("运行").map(([name]) => name)).toEqual(["对话", "消息渠道"]);
      expect(group("能力").map(([name]) => name)).toEqual([
        "MCP 服务器",
        "自定义工具",
        "技能",
        "命令行工具",
      ]);
      expect(group("上下文").map(([name]) => name)).toEqual(["知识", "记忆"]);
      expect(group("系统").map(([name]) => name)).toEqual(["密钥", "活动", "用量", "同步"]);
    } finally {
      await i18n.changeLanguage("en");
    }
  });
});

/** The leaf route a path resolves to in the app's real route table. */
function leafRoute(path: string): string | undefined {
  const matches = matchRoutes(appRoutes, path) ?? [];
  const route = matches[matches.length - 1]?.route;
  return route?.index ? "" : route?.path;
}

/** Whether the leaf route a path resolves to only redirects somewhere else. */
function isRedirect(path: string): boolean {
  const matches = matchRoutes(appRoutes, path) ?? [];
  const element = matches[matches.length - 1]?.route.element;
  return isValidElement(element) && element.type === Navigate;
}

function groupLabels(): string[] {
  return Array.from(document.querySelectorAll(".nav-group-label")).map((n) => n.textContent ?? "");
}

// revise-web-ui-ia: web-ui "the sidebar groups entries by what the user comes to do"
acceptance("web-ui", "the sidebar groups agents, resources and system by role", () => {
  renderNav();

  expect(ungrouped()).toEqual(["Overview"]);
  expect(groupLabels()).toEqual(["Agents", "Run", "Capabilities", "Context", "System"]);
  expect(group("Agents").map(([name]) => name)).toEqual(["Agents", "Model providers"]);
  expect(group("Run").map(([name]) => name)).toEqual(["Conversations", "Channels"]);
  expect(group("Capabilities").map(([name]) => name)).toEqual([
    "MCP servers",
    "Custom tools",
    "Skills",
    "CLIs",
  ]);
  expect(group("Context").map(([name]) => name)).toEqual(["Knowledge", "Memory"]);
  expect(group("System").map(([name]) => name)).toEqual(["Secrets", "Activity", "Usage", "Sync"]);
});

acceptance("web-ui", "every resource entry opens a list page of its own", () => {
  renderNav();

  const hrefs = Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href")!);
  expect(hrefs).toHaveLength(15);
  // The check below can tell a redirect apart: the retired /resources is one.
  expect(isRedirect("/resources")).toBe(true);
  const resolved = hrefs.map((href) => leafRoute(href));
  // Each entry is its own route — the path itself, never the catch-all.
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
  expect(links.length).toBe(15);
  for (const link of links) {
    const href = link.getAttribute("href");
    expect(href).toBeTruthy();
    expect(leafRoute(href!)).not.toBe("*");
    expect(link.textContent ?? "").not.toMatch(/soon|not yet|coming/i);
    expect(link).not.toHaveAttribute("aria-disabled", "true");
    // Settings is a footer row, never an entry.
    expect(href).not.toMatch(/^\/settings/);
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

/** A configured, joined remote that is switched on — a paused one never raises the dot. */
const ON = {
  remote: { enabled: true },
  joined: true,
  conflicts: 0,
  held: 0,
  join_choices: 0,
  problem: null,
};

const HELD = { status: "held", conflicts: 0, held: 3, detail: null };

describe("the Sync attention dot", () => {
  test("is absent while the vault is converging", () => {
    syncStatus.mockReturnValue({
      data: { ...ON, last_round: { status: "pulled", conflicts: 0, held: 0, detail: null } },
      isError: false,
    } as never);
    const { queryByTestId } = renderNav();
    expect(queryByTestId("nav-dot-sync")).toBeNull();
  });

  test("appears when the last round needs answering", async () => {
    syncStatus.mockReturnValue({
      data: { ...ON, held: 3, last_round: HELD },
      isError: false,
    } as never);
    const { findByTestId } = renderNav();
    expect(await findByTestId("nav-dot-sync")).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "an entry without a signal never carries a dot"
  test("only an entry whose kind declares a signal carries the dot, with an accessible name", async () => {
    syncStatus.mockReturnValue({
      data: { ...ON, held: 3, last_round: HELD },
      isError: false,
    } as never);
    const { findByTestId } = renderNav();
    const dot = await findByTestId("nav-dot-sync");
    expect(dot).toHaveAccessibleName("Needs your attention");
    expect(document.querySelectorAll('[data-testid^="nav-dot-"]')).toHaveLength(1);
  });

  acceptance("vault-sync", "a held vault says so where the user already is", async () => {
    syncStatus.mockReturnValue({
      data: { ...ON, held: 3, last_round: HELD },
      isError: false,
    } as never);
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
    syncStatus.mockReturnValue({
      data: { ...ON, held: 3, last_round: HELD },
      isError: true,
    } as never);
    const { queryByTestId } = renderNav();
    expect(queryByTestId("nav-dot-sync")).toBeNull();
  });

  test("survives a collapsed rail, where the label is gone", async () => {
    syncStatus.mockReturnValue({
      data: { ...ON, held: 3, last_round: HELD },
      isError: false,
    } as never);
    const { findByTestId } = renderNav("/", true);
    expect(await findByTestId("nav-dot-sync")).toBeInTheDocument();
  });
});

// --- experimental features (spec experimental-features "Close every surface
// of a switched-off feature") ---

describe("a switched-off experimental feature", () => {
  acceptance("web-ui", "a switched-off feature leaves the sidebar", () => {
    features.mockReturnValue({ fake_feature: false, fake_group: true });
    renderNav();

    expect(group("System").map(([name]) => name)).toEqual(["Secrets", "Activity", "Usage", "Sync"]);
    const hrefs = Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href"));
    expect(hrefs).not.toContain("/fake");
    expect(hrefs).toContain("/fake-group");
  });

  test("a switched-on feature's entry is listed", () => {
    features.mockReturnValue({ fake_feature: true, fake_group: false });
    renderNav();

    expect(group("System").map(([name]) => name)).toEqual([
      "Secrets",
      "Activity",
      "Usage",
      "Sync",
      "Fake",
    ]);
  });

  // revise-web-ui-ia: web-ui "a group with every entry switched off leaves the sidebar"
  test("a group with every entry switched off leaves its heading out", () => {
    features.mockReturnValue({ fake_feature: true, fake_group: false });
    renderNav();

    expect(groupLabels()).toEqual(["Agents", "Run", "Capabilities", "Context", "System"]);
  });

  test("an entry whose feature is not known yet is left out rather than flashed in", () => {
    features.mockReturnValue(null);
    renderNav();

    const hrefs = Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href"));
    expect(hrefs).not.toContain("/fake");
    expect(hrefs).not.toContain("/fake-group");
    expect(hrefs).toHaveLength(15);
  });
});

// --- spec experimental-features "Mark an experimental feature's sidebar entry" ---

describe("an experimental feature's entry", () => {
  acceptance(
    "experimental-features",
    "a switched-on feature's entry says it is experimental",
    () => {
      features.mockReturnValue({ fake_feature: true, fake_group: false });
      const { getByTestId, queryByTestId } = renderNav();

      expect(getByTestId("nav-experimental-fake")).toHaveTextContent("Experimental");
      for (const id of [
        "overview",
        "agents",
        "conversations",
        "mcp-servers",
        "skills",
        "channels",
        "knowledge",
        "memory",
        "sync",
      ]) {
        expect(queryByTestId(`nav-experimental-${id}`)).toBeNull();
      }
    },
  );

  test("a collapsed rail leaves the marker to the tooltip, as it does the label", () => {
    features.mockReturnValue({ fake_feature: true, fake_group: false });
    const { queryByTestId, getByRole } = renderNav("/", true);

    expect(queryByTestId("nav-experimental-fake")).toBeNull();
    expect(getByRole("link", { name: "Fake" })).toBeInTheDocument();
  });
});
