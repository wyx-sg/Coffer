// frontend/src/components/agents/AgentMcpServersTab.test.tsx
//
// The MCP-servers tab has two sections:
//   A. "Via Coffer gateway" — install status + a link to the standalone MCP
//      servers page (the exposed servers are managed there, not re-listed here).
//   B. "Direct servers" — name, description (the transport badge + the command
//      line or URL, the only descriptive text an MCP config entry has) and two
//      actions: adopt into Coffer, and delete (confirm -> DELETE with the
//      entry's source). The wire type still carries `enabled` and `source` for
//      the CLI, but neither is a column: `source` shows as a badge only when
//      two rows share a name, which only `claude_code` can do. The `coffer` entry itself
//      is hidden here (it IS the gateway hookup), duplicate-of-Coffer entries
//      get an inline hint (informational only), and unparseable config files
//      surface as a banner.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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
    removeMcpEntry: vi.fn(),
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

// codex-style entry: enabled is a real boolean on the wire (the table shows
// no enabled column either way).
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
  api.removeMcpEntry.mockResolvedValue(undefined);
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

  test("direct entries render name + description; coffer entry hidden; no source or enabled column", async () => {
    stub();
    renderTab();

    expect(await screen.findByText("github")).toBeInTheDocument();
    expect(screen.getByText("fetcher")).toBeInTheDocument();
    // The coffer entry is the gateway hookup — not listed as a direct server.
    expect(screen.queryByText("coffer")).not.toBeInTheDocument();

    // The description column: transport badge + the command line or the URL.
    expect(screen.getByText("npx -y gh-mcp")).toBeInTheDocument();
    expect(screen.getByText("https://example.com/mcp")).toBeInTheDocument();

    // Source stays on the wire (adopt/delete carry it) but has no column, and
    // no badge either while every row's name is unique.
    expect(screen.queryByRole("columnheader", { name: /^source$/i })).not.toBeInTheDocument();
    expect(screen.queryByText("global")).not.toBeInTheDocument();
    expect(screen.queryByText("config")).not.toBeInTheDocument();

    // The enabled flag stays on the wire for the CLI, but the table drops it:
    // no header, no per-row badge or dash, no Switch.
    expect(screen.queryByRole("columnheader", { name: /^enabled$/i })).not.toBeInTheDocument();
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    const codexRow = screen.getByText("fetcher").closest("tr") as HTMLElement;
    expect(within(codexRow).queryByText("Enabled")).not.toBeInTheDocument();
    const claudeRow = screen.getByText("github").closest("tr") as HTMLElement;
    expect(within(claudeRow).queryByText("—")).not.toBeInTheDocument();
  });

  test("a name carried by two config files badges each row with its source", async () => {
    // Only claude_code can do this: the same entry name in ~/.claude.json and
    // in settings.json. Without the badge the two rows are indistinguishable,
    // and adopt/delete act on different files.
    stub({
      items: [
        { ...CLAUDE_ENTRY, source: "global" },
        { ...CLAUDE_ENTRY, source: "settings" },
      ],
    });
    renderTab();

    expect(await screen.findAllByText("github")).toHaveLength(2);
    expect(screen.getByText("global")).toBeInTheDocument();
    expect(screen.getByText("settings")).toBeInTheDocument();
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

  test("every direct entry offers both writes: adopt and delete", async () => {
    stub();
    renderTab();
    await screen.findByText("github");

    // Toggling an entry is gone; adopt + delete are the two per-row actions.
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.getAllByRole("button", { name: "Adopt into Coffer" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(2);
  });

  test("delete flows through the confirm dialog and passes the entry's source", async () => {
    stub();
    renderTab();
    await screen.findByText("github");

    // Rows render in items order → the first Delete belongs to "github".
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(
        /delete this entry from the agent's config file\? a \.bak backup will be written\./i,
      ),
    ).toBeInTheDocument();

    // Nothing is written until the confirm button is pressed.
    expect(api.removeMcpEntry).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(api.removeMcpEntry).toHaveBeenCalledWith("cc", "github", "global"));
  });

  test("cancelling the delete dialog writes nothing", async () => {
    stub();
    renderTab();
    await screen.findByText("github");

    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.removeMcpEntry).not.toHaveBeenCalled();
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

  test("matches_resource renders the duplicate hint as plain text, with no inline shortcut", async () => {
    stub({
      items: [{ ...CODEX_ENTRY, matches_resource: "fetcher" }],
    });
    renderTab();
    expect(await screen.findByText(/already in coffer as fetcher/i)).toBeInTheDocument();
    // The hint is informational — the row's own Delete button is the only way
    // to drop the duplicate, so there is no extra inline shortcut.
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /duplicate/i })).not.toBeInTheDocument();
  });

  test("en and zh locales carry the same agents.workspace.mcp keys", () => {
    const enKeys = Object.keys(en.agents.workspace.mcp).sort();
    const zhKeys = Object.keys(zh.agents.workspace.mcp).sort();
    expect(enKeys.length).toBeGreaterThan(0);
    expect(zhKeys).toEqual(enKeys);
  });
});
