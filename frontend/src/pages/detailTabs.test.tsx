// frontend/src/pages/detailTabs.test.tsx
// Every detail page lays its tabs out the same way: one shared tab strip, the
// open tab named in the URL (`?tab=`), and switching tab rewriting that URL.
// Checked on two detail pages of different kinds side by side.
import { afterEach, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { McpServerDetailTabs } from "@/components/mcp/McpServerDetailTabs";
import { SkillDetailPage } from "./SkillDetailPage";
import type { SkillOut } from "@/lib/api/skills";

// What the tabs SHOW belongs to each kind; stub the heavy bodies so this test
// is about the tab layout alone.
vi.mock("@/components/mcp/CapabilityList", () => ({
  CapabilityList: ({ type }: { type: string }) => <div>{`capability list: ${type}`}</div>,
}));
vi.mock("@/components/mcp/InvocationsTable", () => ({
  InvocationsTable: () => <div>invocations</div>,
}));
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkill: vi.fn(),
  useRemoveSkill: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSkillFiles: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useSkillFileContent: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
}));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: { scope: null, supports_scope: true } })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const skillHooks = await import("@/lib/hooks/useSkills");

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
  last_synced_from_source_at: null,
  created_at: "2026-05-26T00:00:00Z",
  updated_at: "2026-05-26T00:00:00Z",
  bindings: [],
};

const where = { search: "" };
function Probe() {
  where.search = useLocation().search;
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
  // An MCP server's detail tabs, opened on Tools by the URL.
  const mcp = renderRoute(
    "/mcp-servers/u-1?tab=tools",
    "/mcp-servers/:uid",
    <McpServerDetailTabs
      serverUid="u-1"
      capabilities={undefined}
      config={{ transport: { type: "stdio", command: "npx" } }}
      isCapsPending={false}
      onRefresh={vi.fn()}
    />,
  );
  const mcpStrip = strip();
  expect(mcpStrip.selected).toHaveTextContent("Tools");
  fireEvent.mouseDown(within(mcpStrip.list).getByRole("tab", { name: "Prompts" }));
  expect(where.search).toBe("?tab=prompts");
  const mcpClass = mcpStrip.list.className;
  mcp.unmount();

  // A skill's detail page, opened on Files by the URL.
  vi.mocked(skillHooks.useSkill).mockReturnValue({
    data: SKILL,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof skillHooks.useSkill>);
  renderRoute("/skills/sk-1?tab=files", "/skills/:uid", <SkillDetailPage />);
  const skillStrip = strip();
  expect(skillStrip.selected).toHaveTextContent("Files");
  fireEvent.mouseDown(within(skillStrip.list).getByRole("tab", { name: "Overview" }));
  // The default tab is the bare URL on both pages.
  expect(where.search).toBe("");

  expect(skillStrip.list.className).toBe(mcpClass);
});

acceptance("web-ui", "a server's detail page opens on its Overview", () => {
  renderRoute(
    "/mcp-servers/u-1",
    "/mcp-servers/:uid",
    <McpServerDetailTabs
      serverUid="u-1"
      capabilities={undefined}
      config={{ transport: { type: "stdio", command: "npx", args: ["-y", "srv"] } }}
      isCapsPending={false}
      onRefresh={vi.fn()}
    />,
  );

  const { list, selected } = strip();
  expect(selected).toHaveTextContent("Overview");
  expect(
    within(list)
      .getAllByRole("tab")
      .map((t) => t.textContent),
  ).toEqual(["Overview", "Tools", "Resources", "Prompts", "Invocations"]);
  // The Overview pane is what is showing: what the server runs, not a toggle list.
  expect(screen.getByText("npx -y srv")).toBeVisible();
  expect(screen.queryByText(/capability list/)).not.toBeInTheDocument();
});
