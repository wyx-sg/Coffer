// frontend/src/components/agents/AgentMcpServersTab.test.tsx
//
// The MCP-servers tab has two sections:
//   A. "Via Coffer gateway" — install status + the enabled mcp_server
//      resources Coffer exposes through the gateway (read-only list).
//   B. "Direct servers" — the agent's own MCP entries with source/transport,
//      a per-entry Switch only where the agent supports it (codex-style
//      entries carry enabled: true/false; claude entries carry null), adopt
//      into Coffer, and remove (confirm → DELETE with the entry's source).
//      The `coffer` entry itself is hidden here (it IS the gateway hookup),
//      duplicate-of-Coffer entries get an inline hint + remove-duplicate
//      shortcut, and unparseable config files surface as a banner.
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
    toggleMcpEntry: vi.fn(),
    removeMcpEntry: vi.fn(),
    adoptMcpEntry: vi.fn(),
  },
}));
vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(() => ({
    data: [
      {
        ref: { kind: "mcp_server", name: "fs" },
        kind: "mcp_server",
        name: "fs",
        description: null,
        config: {},
        enabled: true,
        created_at: "",
        updated_at: "",
      },
    ],
    isPending: false,
    error: null,
  })),
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
  api.toggleMcpEntry.mockResolvedValue(undefined);
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
  test("gateway section lists the exposed servers; not-installed shows the note", async () => {
    stub();
    renderTab();
    expect(await screen.findByText("fs")).toBeInTheDocument();
    expect(screen.getByText("Via Coffer gateway")).toBeInTheDocument();

    api.mcpStatus.mockResolvedValue({ installed: false, command: null });
    renderTab();
    expect(
      await screen.findAllByText(/coffer mcp isn't installed on this agent/i),
    ).not.toHaveLength(0);
  });

  test("direct entries render source + transport; coffer entry hidden; Switch only for codex-style entries", async () => {
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

    // Only the codex-style entry (enabled !== null) gets a Switch.
    expect(screen.getAllByRole("switch")).toHaveLength(1);
    expect(screen.getByRole("switch", { name: /fetcher/ })).toBeInTheDocument();
  });

  test("toggling the Switch calls the API with the flipped enabled flag", async () => {
    stub();
    renderTab();
    fireEvent.click(await screen.findByRole("switch"));
    await waitFor(() => expect(api.toggleMcpEntry).toHaveBeenCalledWith("cc", "fetcher", false));
  });

  test("remove flows through the confirm dialog and passes the entry's source", async () => {
    stub();
    renderTab();
    await screen.findByText("github");

    // Rows render in items order → the first Remove belongs to "github".
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/remove this entry\? a \.bak backup will be written\./i),
    ).toBeInTheDocument();

    expect(api.removeMcpEntry).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.removeMcpEntry).toHaveBeenCalledWith("cc", "github", "global"));
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

  test("matches_resource renders the duplicate hint + remove-duplicate shortcut", async () => {
    stub({
      items: [{ ...CODEX_ENTRY, matches_resource: "fetcher" }],
    });
    renderTab();
    expect(await screen.findByText(/already in coffer as fetcher/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove duplicate" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.removeMcpEntry).toHaveBeenCalledWith("cc", "fetcher", "config"));
  });

  test("en and zh locales carry the same agents.workspace.mcp keys", () => {
    const enKeys = Object.keys(en.agents.workspace.mcp).sort();
    const zhKeys = Object.keys(zh.agents.workspace.mcp).sort();
    expect(enKeys.length).toBeGreaterThan(0);
    expect(zhKeys).toEqual(enKeys);
  });
});
