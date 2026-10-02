// frontend/src/pages/detailTabs.test.tsx
// Every detail page lays its tabs out the same way: one shared tab strip, the
// open tab named in the path (`/<kind>/<id>/<tab>`, the default tab at the
// bare `/<kind>/<id>`), and switching tab rewriting that path.
// Checked on two detail pages of different kinds side by side.
import { afterEach, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { McpServerDetailTabs } from "@/components/mcp/McpServerDetailTabs";
import { SkillDetailPane } from "@/components/skills/SkillDetailPane";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { SkillOut } from "@/lib/api/skills";
import { useDetailTab } from "@/lib/detailTabs";
import { SKILL_TABS } from "@/lib/skills/tabs";

// What the tabs SHOW belongs to each kind; stub the heavy bodies so this test
// is about the tab layout alone.
vi.mock("@/components/mcp/CapabilityList", () => ({
  CapabilityList: ({ type }: { type: string }) => <div>{`capability list: ${type}`}</div>,
}));
vi.mock("@/lib/hooks/useSkills", () => ({
  useRemoveSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSkillFiles: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useSkillFileContent: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useSkillCopies: vi.fn(() => ({ data: undefined, isFetching: false, refetch: vi.fn() })),
  useCheckSkillSource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useReadSkillFileNow: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useWriteSkillFile: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: { scope: null, supports_scope: true } })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useBulkReach: vi.fn(() => ({ disable: vi.fn(), enable: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useSetResourceTitle: vi.fn(() => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn().mockResolvedValue({}),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const SKILL: SkillOut = {
  uid: "sk-1",
  name: "hello",
  description: "a greeting",
  source: { type: "local_import", original_path: "/tmp/hello" },
  builtin: false,
  enabled: true,
  scope: null,
  version_hash: "deadbeefcafe1234",
  master_path: "/master/hello",
  master_missing: false,
  last_synced_from_source_at: null,
  created_at: "2026-05-26T00:00:00Z",
  updated_at: "2026-05-26T00:00:00Z",
  bindings: [],
  requires: [],
  requires_secrets: [],
  source_status: null,
};

/** The skill's reading pane, its tab addressed the way the Skills page does. */
function SkillTabs({ name = "hello" }: { name?: string }) {
  const [tab, setTab] = useDetailTab(SKILL_TABS, "files", `/skills/${name}`);
  return (
    <TooltipProvider>
      <SkillDetailPane
        skill={{ ...SKILL, name }}
        tab={tab}
        onTabChange={setTab}
        onDeleted={vi.fn()}
      />
    </TooltipProvider>
  );
}

function ServerTabs({ name }: { name: string }) {
  return (
    <McpServerDetailTabs
      basePath={`/mcp-servers/${name}`}
      counts={{}}
      overview={<div>server overview</div>}
      tools={<div>server tools</div>}
      resources={null}
      prompts={null}
      invocations={null}
    />
  );
}

const where = { url: "" };
function Probe() {
  const loc = useLocation();
  where.url = loc.pathname + loc.search;
  return null;
}

function renderRoute(path: string, route: string, element: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path={route}
            element={
              <>
                {element}
                <Probe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

/** The one tab strip on screen, its selected tab, and its class list. */
function strip() {
  const lists = screen.getAllByRole("tablist");
  expect(lists).toHaveLength(1);
  const selected = within(lists[0])
    .getAllByRole("tab")
    .filter((t) => t.getAttribute("aria-selected") === "true");
  expect(selected).toHaveLength(1);
  return { list: lists[0], selected: selected[0] };
}

acceptance("web-ui", "detail pages share one tab layout", () => {
  // An MCP server's detail tabs, opened on Tools by the path.
  const mcp = renderRoute(
    "/mcp-servers/srv/tools",
    "/mcp-servers/:name/:tab?",
    <McpServerDetailTabs
      basePath="/mcp-servers/srv"
      counts={{}}
      overview={<div>server overview</div>}
      tools={<div>server tools</div>}
      resources={null}
      prompts={null}
      invocations={null}
    />,
  );
  const mcpStrip = strip();
  expect(mcpStrip.selected).toHaveTextContent("Tools");
  fireEvent.mouseDown(within(mcpStrip.list).getByRole("tab", { name: "Prompts" }));
  expect(where.url).toBe("/mcp-servers/srv/prompts");
  const mcpClass = mcpStrip.list.className;
  mcp.unmount();

  // A skill's detail pane, opened on History by the path.
  renderRoute("/skills/hello/history", "/skills/:name/:tab?", <SkillTabs />);
  const skillStrip = strip();
  expect(skillStrip.selected).toHaveTextContent("History");
  fireEvent.mouseDown(within(skillStrip.list).getByRole("tab", { name: "Files" }));
  // The default tab is the bare address on both pages.
  expect(where.url).toBe("/skills/hello");

  expect(skillStrip.list.className).toBe(mcpClass);
});

acceptance("web-ui", "a detail tab lives in the path", () => {
  // The bare address opens each page on its default tab.
  const skill = renderRoute(
    "/skills/release-notes",
    "/skills/:name/:tab?",
    <SkillTabs name="release-notes" />,
  );
  expect(strip().selected).toHaveTextContent("Files");
  fireEvent.mouseDown(within(strip().list).getByRole("tab", { name: "Delivery" }));
  expect(where.url).toBe("/skills/release-notes/delivery");
  expect(strip().selected).toHaveTextContent("Delivery");
  skill.unmount();

  renderRoute("/mcp-servers/github", "/mcp-servers/:name/:tab?", <ServerTabs name="github" />);
  expect(strip().selected).toHaveTextContent("Overview");
  fireEvent.mouseDown(within(strip().list).getByRole("tab", { name: "Tools" }));
  expect(where.url).toBe("/mcp-servers/github/tools");
  expect(strip().selected).toHaveTextContent("Tools");
});

acceptance("web-ui", "a server's detail page opens on its Overview", () => {
  renderRoute(
    "/mcp-servers/srv",
    "/mcp-servers/:name/:tab?",
    <McpServerDetailTabs
      basePath="/mcp-servers/srv"
      counts={{}}
      overview={<div>npx -y srv</div>}
      tools={<div>server tools</div>}
      resources={null}
      prompts={null}
      invocations={null}
    />,
  );

  const { list, selected } = strip();
  expect(selected).toHaveTextContent("Overview");
  expect(
    within(list)
      .getAllByRole("tab")
      .map((t) => t.textContent),
  ).toEqual(["Overview", "Tools", "Resources", "Prompts", "Invocations"]);
  // The Overview pane is what is showing, not the tools list.
  expect(screen.getByText("npx -y srv")).toBeVisible();
  expect(screen.queryByText("server tools")).not.toBeInTheDocument();
  expect(screen.queryByText(/capability list/)).not.toBeInTheDocument();
});
