// src/components/SidebarNavAttention.test.tsx — the sidebar's count badges over the real SidebarNav (spec web-ui
// "Mark a sidebar entry whose kind needs attention").
//
// The three reads behind the badges are stubbed at their hooks' edges: the
// cross-kind attention list, the vault's sync status and the CLIs list. The
// counting (`useAttentionSignals`) and the rendering (`AttentionDot`, the rail
// tooltip) are real.
import { afterEach, beforeEach, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SidebarNav } from "./SidebarNav";

const attention = vi.fn(
  (): { data: { items: { kind: string; severity: string }[] } | undefined } => ({
    data: undefined,
  }),
);
vi.mock("@/lib/hooks/useAttention", () => ({ useAttention: () => attention() }));

const syncStatus = vi.fn((): { data: unknown; isError: boolean } => ({
  data: undefined,
  isError: false,
}));
vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: () => syncStatus() }));

vi.mock("@/lib/api/clis", () => ({ clisApi: { list: vi.fn() } }));
const { clisApi } = await import("@/lib/api/clis");

// The Skills badge counts the skills list itself; unreadable unless a test sets it.
vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: { list: vi.fn(), orphans: vi.fn(), verify: vi.fn() },
}));
const { skillsApi } = await import("@/lib/api/skills");

vi.mock("@/lib/hooks/useFeatures", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useFeatures")>()),
  useFeatureMap: () => ({ knowledge: true, memory: true, sync: true, models: true }),
  useFeatureEnabled: () => true,
}));

/** A joined, switched-on remote whose last round is held for confirmation. */
const HELD_VAULT = {
  remote: { enabled: true },
  joined: true,
  conflicts: 0,
  held: 3,
  join_choices: 0,
  problem: null,
  last_round: { status: "held", conflicts: 0, held: 3, detail: null },
};

const item = (kind: string, severity: string) => ({ kind, severity });

beforeEach(() => {
  vi.mocked(clisApi.list).mockResolvedValue({ items: [], warnings: [] });
  vi.mocked(skillsApi.list).mockRejectedValue(new Error("offline"));
  vi.mocked(skillsApi.orphans).mockResolvedValue({ items: [] });
});
afterEach(() => {
  vi.clearAllMocks();
  attention.mockReset();
  attention.mockReturnValue({ data: undefined });
  syncStatus.mockReset();
  syncStatus.mockReturnValue({ data: undefined, isError: false });
  localStorage.clear();
});

function renderNav(at = "/agents", collapsed = false) {
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

const badges = () => Array.from(document.querySelectorAll('[data-testid^="nav-dot-"]'));

acceptance("web-ui", "an entry whose kind needs attention carries a count badge", async () => {
  syncStatus.mockReturnValue({ data: HELD_VAULT, isError: false });
  attention.mockReturnValue({
    data: { items: [item("mcp_server", "warning"), item("mcp_server", "error")] },
  });
  renderNav("/agents");

  const sync = await screen.findByTestId("nav-dot-sync");
  expect(sync).toHaveTextContent("1");
  expect(sync).toHaveAccessibleName("Needs your attention");
  const mcp = screen.getByTestId("nav-dot-mcp-servers");
  expect(mcp).toHaveTextContent("2");
  expect(mcp).toHaveClass("bg-danger-strong");
  expect(sync).toHaveClass("bg-danger-strong");
  expect(mcp).toHaveAccessibleName("Needs your attention");
  expect(badges()).toHaveLength(2);
});

acceptance("web-ui", "the attention dot stays on the collapsed rail", async () => {
  attention.mockReturnValue({ data: { items: [item("mcp_server", "error")] } });
  renderNav("/agents", true);

  const dot = screen.getByTestId("nav-dot-mcp-servers");
  expect(dot).toHaveTextContent("");
  expect(dot).toHaveClass("bg-danger-strong");
  fireEvent.focus(screen.getByRole("link", { name: "MCP servers" }));
  expect(await screen.findByRole("tooltip")).toHaveTextContent("MCP servers · 1 needs you");
});

acceptance("web-ui", "an entry without a signal never carries a badge", async () => {
  // Every kind's signal raised, plus what must never badge: items waiting in
  // a knowledge collection, memory, and an informational item.
  syncStatus.mockReturnValue({ data: HELD_VAULT, isError: false });
  attention.mockReturnValue({
    data: {
      items: [
        item("agent", "warning"),
        item("agent", "info"),
        item("provider", "warning"),
        item("channel", "warning"),
        item("mcp_server", "warning"),
        item("skill", "warning"),
        item("knowledge", "warning"),
        item("memory", "warning"),
        item("custom_tool", "warning"),
      ],
    },
  });
  vi.mocked(clisApi.list).mockResolvedValue({
    items: [
      {
        command: "gh",
        status: "outdated",
        needed_by: ["code-review"],
        needed_by_servers: [],
        added: false,
      },
    ],
    warnings: [],
  } as never);
  renderNav("/");

  await screen.findByTestId("nav-dot-clis");
  const badged = badges().map((b) => b.getAttribute("data-testid"));
  expect(badged.sort()).toEqual(
    [
      "nav-dot-agents",
      "nav-dot-model-providers",
      "nav-dot-channels",
      "nav-dot-mcp-servers",
      "nav-dot-skills",
      "nav-dot-sync",
      "nav-dot-clis",
    ].sort(),
  );
  expect(screen.queryByTestId("nav-dot-knowledge")).toBeNull();
  expect(screen.queryByTestId("nav-dot-memory")).toBeNull();
  // The informational agent item is not counted beside the warning one.
  expect(screen.getByTestId("nav-dot-agents")).toHaveTextContent("1");
});

acceptance(
  "web-ui",
  "the Skills badge counts skills needing attention plus folders no skill claims",
  async () => {
    // Two skills with a problem (a master gone; a tool off), one that is fine and
    // one with only an update waiting, and one folder in the store no skill claims.
    const skill = (name: string, over: Record<string, unknown>) =>
      ({
        uid: name,
        name,
        builtin: false,
        enabled: true,
        scope: null,
        master_missing: false,
        requires: [],
        requires_secrets: [],
        requires_tools: [],
        requires_skills: [],
        bindings: [],
        source_status: null,
        ...over,
      }) as never;
    vi.mocked(skillsApi.list).mockResolvedValue({
      items: [
        skill("gone", { master_missing: true }),
        skill("tool-off", {
          requires_tools: [
            { name: "github", uid: "t", kind: "mcp_server", status: "off", why: null },
          ],
        }),
        skill("fine", {}),
        skill("updating", { source_status: { error: null, update_available: true } }),
      ],
    });
    vi.mocked(skillsApi.orphans).mockResolvedValue({
      items: [
        {
          name: "lint-rules",
          path: "/p",
          valid: true,
          file_count: 1,
          description: null,
          message: null,
        },
      ],
    });
    renderNav("/");
    const dot = await screen.findByTestId("nav-dot-skills");
    expect(dot).toHaveTextContent("3");
  },
);

acceptance("web-ui", "an unreadable signal leaves no badge", async () => {
  // Nothing answered yet, a failing sync read and a failing CLIs read.
  attention.mockReturnValue({ data: undefined });
  syncStatus.mockReturnValue({ data: HELD_VAULT, isError: true });
  vi.mocked(clisApi.list).mockRejectedValue(new Error("offline"));
  renderNav("/");

  await vi.waitFor(() => expect(clisApi.list).toHaveBeenCalled());
  await new Promise((r) => setTimeout(r, 20));
  expect(badges()).toHaveLength(0);
  expect(document.body.textContent ?? "").not.toMatch(/error|couldn.t|failed/i);
});

acceptance("web-ui", "the badge count caps at 9+", async () => {
  attention.mockReturnValue({
    data: { items: Array.from({ length: 12 }, () => item("mcp_server", "warning")) },
  });
  renderNav("/agents");

  const badge = await screen.findByTestId("nav-dot-mcp-servers");
  expect(badge).toHaveTextContent("9+");
  expect(badge).toHaveClass("bg-danger-strong");
});
