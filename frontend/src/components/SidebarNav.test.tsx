// frontend/src/components/SidebarNav.test.tsx
// The sidebar's information architecture, which is a product decision and not
// a styling one: Overview, then five groups by what the user comes to do
// (ADR sidebar-grouped-by-what-the-person-comes-to-do).

import { afterEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { act, render, within } from "@testing-library/react";
import { isValidElement } from "react";
import { MemoryRouter, Navigate, matchRoutes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarNav } from "./SidebarNav";
import { appRoutes } from "@/router";

// The four experimental features (knowledge, memory, sync, models) own five of
// the fourteen entries. All are on unless a test says otherwise, so every other
// assertion here is about the full fourteen.
const ALL_ON: Record<string, boolean> = {
  knowledge: true,
  memory: true,
  sync: true,
  models: true,
};
const features = vi.fn((): Record<string, boolean> | null => ALL_ON);
vi.mock("@/lib/hooks/useFeatures", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useFeatures")>()),
  useFeatureMap: () => features(),
  useFeatureEnabled: (key: string) => {
    const map = features();
    return map === null ? undefined : map[key] === true;
  },
}));

afterEach(() => {
  features.mockReturnValue(ALL_ON);
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

/** A row's name: its visible text. */
function entryName(link: HTMLElement): string {
  return link.textContent ?? "";
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
  acceptance("web-ui", "each listed resource kind has one sidebar entry", () => {
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
    // MCP servers and Custom tools are two entries opening two pages.
    const href = (name: string) =>
      Array.from(document.querySelectorAll("nav a"))
        .find((a) => entryName(a as HTMLElement) === name)
        ?.getAttribute("href");
    expect(href("MCP servers")).toBe("/mcp-servers");
    expect(href("Custom tools")).toBe("/custom-tools");
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
      expect(group("系统").map(([name]) => name)).toEqual(["密钥", "活动", "同步"]);
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

acceptance("web-ui", "the sidebar groups entries by what the user comes to do", () => {
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
  expect(group("System").map(([name]) => name)).toEqual(["Secrets", "Activity", "Sync"]);
});

acceptance("web-ui", "every resource entry opens a list page of its own", () => {
  renderNav();

  const hrefs = Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href")!);
  expect(hrefs).toHaveLength(14);
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
  expect(links.length).toBe(14);
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

// --- experimental features (spec experimental-features "Make a switched-off
// feature look absent in the UI") ---

/** Every sidebar link's address. */
const hrefs = () =>
  Array.from(document.querySelectorAll("nav a")).map((a) => a.getAttribute("href"));

/** Which addresses each feature owns. */
const OWNED: Record<string, string[]> = {
  models: ["/model-providers"],
  knowledge: ["/knowledge"],
  memory: ["/memory"],
  sync: ["/sync"],
};

describe("a switched-off experimental feature", () => {
  acceptance(
    "experimental-features",
    "a switched-off feature is absent from the navigation",
    () => {
      for (const [feature, owned] of Object.entries(OWNED)) {
        features.mockReturnValue({ ...ALL_ON, [feature]: false });
        const view = renderNav();

        const shown = hrefs();
        for (const to of owned) expect(shown).not.toContain(to);
        // The other features' entries stay.
        for (const [other, entries] of Object.entries(OWNED)) {
          if (other !== feature) for (const to of entries) expect(shown).toContain(to);
        }
        expect(shown).toHaveLength(14 - owned.length);
        view.unmount();
      }
    },
  );

  acceptance("web-ui", "a switched-off feature leaves the sidebar", () => {
    features.mockReturnValue({ knowledge: false, memory: false, models: false, sync: false });
    renderNav();

    expect(hrefs()).toEqual([
      "/",
      "/agents",
      "/conversations",
      "/channels",
      "/mcp-servers",
      "/custom-tools",
      "/skills",
      "/clis",
      "/secrets",
      "/activity",
    ]);
  });

  acceptance("web-ui", "a group with every entry switched off leaves the sidebar", () => {
    features.mockReturnValue({ ...ALL_ON, knowledge: false, memory: false });
    renderNav();

    // Context holds only Knowledge and Memory: its heading goes with them.
    expect(groupLabels()).toEqual(["Agents", "Run", "Capabilities", "System"]);
    // A group with an entry left keeps its heading, even when one of its two is off.
    features.mockReturnValue({ ...ALL_ON, knowledge: false });
    const one = renderNav();
    expect(group("Context").map(([name]) => name)).toEqual(["Memory"]);
    one.unmount();
  });

  test("an entry whose feature is not known yet is left out rather than flashed in", () => {
    features.mockReturnValue(null);
    renderNav();

    expect(hrefs()).toHaveLength(10);
    expect(hrefs()).not.toContain("/knowledge");
  });
});

// --- spec experimental-features "Mark an experimental feature's sidebar entry" ---

describe("an experimental feature's entry", () => {
  acceptance(
    "experimental-features",
    "a collapsed rail's tooltip says a feature's entry is experimental",
    async () => {
      const expanded = renderNav();
      // The expanded row stays plain: no tag beside the label.
      for (const name of ["Knowledge", "Memory", "Sync", "Model providers"]) {
        expect(expanded.getByRole("link", { name })).toHaveTextContent(new RegExp(`^${name}$`));
      }
      expanded.unmount();

      const rail = renderNav("/", true);
      act(() => rail.getByRole("link", { name: "Knowledge" }).focus());
      expect(await rail.findByRole("tooltip")).toHaveTextContent("Knowledge · Experimental");
      rail.unmount();

      // An entry no feature owns names no marker in its tooltip.
      const plain = renderNav("/", true);
      act(() => plain.getByRole("link", { name: "Agents" }).focus());
      expect(await plain.findByRole("tooltip")).not.toHaveTextContent("Experimental");
    },
  );
});
