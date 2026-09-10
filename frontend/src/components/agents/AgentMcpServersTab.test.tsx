// frontend/src/components/agents/AgentMcpServersTab.test.tsx
//
// The MCP-servers tab has two sections:
//   A. "Via Coffer gateway" — install status + a link to the standalone MCP
//      servers page (the exposed servers are managed there, not re-listed here).
//   B. "Direct servers" — the agent's own MCP entries with source/transport,
//      a read-only enabled badge where the agent's format has one (codex-style
//      entries carry enabled: true/false; claude entries carry null), and the
//      one write: adopt into Coffer. Removing and toggling an entry are gone —
//      Coffer no longer edits another tool's private config — so the listing
//      offers neither. The `coffer` entry itself is hidden here (it IS the
//      gateway hookup), duplicate-of-Coffer entries get an inline hint, and
//      unparseable config files surface as a banner.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentMcpServersTab } from "./AgentMcpServersTab";
import type { McpEntriesResponse, McpEntryOut } from "@/lib/api/agents";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    mcpStatus: vi.fn(),
    mcpEntries: vi.fn(),
    adoptMcpEntry: vi.fn(),
  },
}));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const ENTRY_BASE = {
  command: null,
  args: [] as string[],
  env_keys: [] as string[],
  secret_keys: [] as string[],
  url: null,
  header_keys: [] as string[],
  is_coffer: false,
  matches_resource: null,
};

const COFFER_ENTRY: McpEntryOut = {
  ...ENTRY_BASE,
  name: "coffer",
  source: "global",
  transport: "stdio",
  command: "/opt/coffer-mcp-shim",
  enabled: null,
  is_coffer: true,
};

// claude_code-style entry: no per-entry enable flag → enabled is null.
const CLAUDE_ENTRY: McpEntryOut = {
  ...ENTRY_BASE,
  name: "github",
  source: "global",
  transport: "stdio",
  command: "npx",
  args: ["-y", "gh-mcp"],
  enabled: null,
};

// codex-style entry: enabled is a real boolean → Switch rendered.
const CODEX_ENTRY: McpEntryOut = {
  ...ENTRY_BASE,
  name: "fetcher",
  source: "config",
  transport: "http",
  url: "https://example.com/mcp",
  enabled: true,
};

function stub(entries: Partial<McpEntriesResponse> = {}) {
  api.mcpStatus.mockResolvedValue({ installed: true, command: "/opt/coffer-mcp-shim" });
  api.mcpEntries.mockResolvedValue({
    items: [COFFER_ENTRY, CLAUDE_ENTRY, CODEX_ENTRY],
    parse_errors: [],
    ...entries,
  });
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(<AgentMcpServersTab agentName="cc" />, { wrapper: Wrapper });
}

afterEach(() => vi.clearAllMocks());

describe("AgentMcpServersTab", () => {
  test("gateway section links to the MCP servers page; not-installed shows the note", async () => {
    stub();
    renderTab();
    expect(screen.getByText("Via Coffer gateway")).toBeInTheDocument();
    // Installed → a link to the standalone page, not a re-listing of servers.
    expect(
      await screen.findByRole("button", { name: /open the mcp servers page/i }),
    ).toBeInTheDocument();

    api.mcpStatus.mockResolvedValue({ installed: false, command: null });
    renderTab();
    expect(
      await screen.findAllByText(/coffer mcp isn't installed on this agent/i),
    ).not.toHaveLength(0);
  });

  test("direct entries render source + transport; coffer entry hidden; enabled shown read-only", async () => {
    stub();
    renderTab();

    expect(await screen.findByText("github")).toBeInTheDocument();
    expect(screen.getByText("fetcher")).toBeInTheDocument();
    // The coffer entry is the gateway hookup — not listed as a direct server.
    expect(screen.queryByText("coffer")).not.toBeInTheDocument();

    // Source + transport badges and the command/url snippet.
    expect(screen.getByText("global")).toBeInTheDocument();
    expect(screen.getByText("config")).toBeInTheDocument();
    expect(screen.getByText("npx -y gh-mcp")).toBeInTheDocument();
    expect(screen.getByText("https://example.com/mcp")).toBeInTheDocument();

    // The enabled state is reported, never offered as a control: the codex-style
    // entry (enabled !== null) shows a badge, the claude one (null) a dash.
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    const codexRow = screen.getByText("fetcher").closest("tr") as HTMLElement;
    expect(within(codexRow).getByText("Enabled")).toBeInTheDocument();
    const claudeRow = screen.getByText("github").closest("tr") as HTMLElement;
    expect(within(claudeRow).getByText("—")).toBeInTheDocument();
  });

  test("the direct-servers search filters rows by name", async () => {
    stub();
    renderTab();

    // Both direct entries visible before filtering.
    expect(await screen.findByText("github")).toBeInTheDocument();
    expect(screen.getByText("fetcher")).toBeInTheDocument();

    // The direct table carries the only "Search servers" box now (the gateway
    // section is a link, not a table).
    const searchBoxes = screen.getAllByPlaceholderText("Search servers");
    fireEvent.change(searchBoxes[searchBoxes.length - 1], { target: { value: "github" } });

    expect(screen.getByText("github")).toBeInTheDocument();
    expect(screen.queryByText("fetcher")).not.toBeInTheDocument();
  });

  test("offers no remove or toggle affordance — adopt is the only write", async () => {
    stub();
    renderTab();
    await screen.findByText("github");

    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /^remove/i })).not.toBeInTheDocument();
    // Every direct entry still offers Adopt into Coffer.
    expect(screen.getAllByRole("button", { name: "Adopt into Coffer" })).toHaveLength(2);
  });

  test("parse_errors render the degraded-config banner", async () => {
    stub({
      parse_errors: [{ source: "settings", path: "/home/u/.claude.json", error: "bad json" }],
    });
    renderTab();
    expect(
      await screen.findByText(/failed to parse config — this file is read-only/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/settings: bad json/)).toBeInTheDocument();
  });

  test("matches_resource renders the duplicate hint, with no remove shortcut", async () => {
    stub({
      items: [{ ...CODEX_ENTRY, matches_resource: "fetcher" }],
    });
    renderTab();
    expect(await screen.findByText(/already in coffer as fetcher/i)).toBeInTheDocument();
    // The hint is informational now — dropping the duplicate is the user's job,
    // in their own tool.
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  test("en and zh locales carry the same agents.workspace.mcp keys", () => {
    const enKeys = Object.keys(en.agents.workspace.mcp).sort();
    const zhKeys = Object.keys(zh.agents.workspace.mcp).sort();
    expect(enKeys.length).toBeGreaterThan(0);
    expect(zhKeys).toEqual(enKeys);
  });
});
