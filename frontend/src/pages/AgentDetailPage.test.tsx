// frontend/src/pages/AgentDetailPage.test.tsx
//
// The page is reached as `/agents/:uid`, so the fixture agent's uid (`u-cur`)
// is deliberately not its name (`cur`): the heading reads the name, and every
// request the page and its dialogs make is addressed to the uid.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AgentDetailPage } from "./AgentDetailPage";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgent: vi.fn(),
  useAgents: vi.fn(() => ({ data: [] })),
  usePatchAgent: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveAgent: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // Stubs for the (lazily-mounted) Config files + MCP surfaces.
  useAgentConfigFiles: vi.fn(() => ({ data: [], isPending: false, error: null })),
  useAgentConfigFile: vi.fn(() => ({ data: undefined, isPending: false })),
  useAgentConfigChild: vi.fn(() => ({ data: undefined, isPending: false })),
  useAgentPlugins: vi.fn(() => ({ data: undefined, isPending: false, error: null })),
  useTogglePlugin: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUninstallPlugin: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useAgentMcpStatus: vi.fn(() => ({ data: { installed: false }, isPending: false })),
  useAgentMcpInstall: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
}));
// The edit form renames through the kind-agnostic resource PATCH, so that
// module is stubbed too. All four writes are declared, not just the rename:
// a factory that omitted one would fail any render that reached for it.
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRenameResource: vi.fn(() => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    error: null,
  })),
}));
const hooks = await import("@/lib/hooks/useAgents");
const useAgentMock = vi.mocked(hooks.useAgent);
const resourceHooks = await import("@/lib/hooks/useResourceMutations");

const AGENT = {
  uid: "u-cur",
  name: "cur",
  type: "codex" as const,
  config_dir: "/home/u/.codex",
  description: null,
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

function mockAgentLoaded() {
  useAgentMock.mockReturnValue({
    data: AGENT,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useAgent>);
}

function renderAt(path = "/agents/u-cur") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/agents/:uid" element={<AgentDetailPage />} />
          <Route path="/agents" element={<div>agents list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentDetailPage header and tab routing", () => {
  test("header shows a back link, the type as a product name, and actions ordered MCP · Edit · Delete", () => {
    mockAgentLoaded();
    renderAt();
    expect(screen.getByRole("link", { name: /back to agents/i })).toHaveAttribute(
      "href",
      "/agents",
    );
    // Product name in the header chip (and again on the overview), never the key.
    expect(screen.getAllByText("Codex").length).toBeGreaterThan(0);
    expect(screen.queryByText("codex")).not.toBeInTheDocument();
    const names = screen
      .getAllByRole("button")
      .map((b) => b.textContent?.trim() ?? "")
      .filter((n) => /coffer mcp|^edit$|^delete$/i.test(n));
    expect(names).toEqual(["Install Coffer MCP", "Edit", "Delete"]);
  });

  test("?tab= opens that tab and clicking a tab writes it to the URL", () => {
    mockAgentLoaded();
    renderAt("/agents/u-cur?tab=plugins");
    expect(screen.getByRole("tab", { name: /^plugins$/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // Radix tabs activate on mousedown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /config files/i }));
    expect(screen.getByRole("tab", { name: /config files/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("an unknown ?tab= falls back to the overview", () => {
    mockAgentLoaded();
    renderAt("/agents/u-cur?tab=nope");
    expect(screen.getByRole("tab", { name: /overview/i })).toHaveAttribute("aria-selected", "true");
  });
});

describe("AgentDetailPage", () => {
  test("renders the header, all seven workspace tabs, and the overview by default", () => {
    mockAgentLoaded();

    renderAt();

    expect(screen.getByRole("heading", { name: "cur" })).toBeInTheDocument();

    // The seven workspace tabs. Plugins is the only one that acts on the agent;
    // Memory and Conversations are read-only views of what it keeps on disk.
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^skills$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^plugins$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^memory$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /conversations/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /config files/i })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(7);

    // Categories that were never built keep their absence pinned.
    expect(screen.queryByRole("tab", { name: /subagents & commands/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /memory & rules/i })).not.toBeInTheDocument();
    // The Instructions tab was removed as redundant with Config files; master-
    // instructions delivery stays available via the API/CLI.
    expect(screen.queryByRole("tab", { name: /instructions/i })).not.toBeInTheDocument();

    // The Coffer-MCP install control lives in the header.
    expect(screen.getByRole("button", { name: /install coffer mcp/i })).toBeInTheDocument();
    // Overview (default tab) shows the config directory but no Skill directory row.
    expect(screen.getByText("/home/u/.codex")).toBeInTheDocument();
    expect(screen.queryByText(/skill directory/i)).not.toBeInTheDocument();
  });

  // `agent` declares no scope (ADR per-agent-resource-scope) — it is not a resource other agents
  // draw on, so there is no activation scope to edit. The page mounts no
  // ScopeControl at all: an agent's own enable/disable is not a header concern
  // here, so not even the control's no-scope enable/disable fallback appears.
  test("mounts no scope control for the agent", () => {
    mockAgentLoaded();
    renderAt();
    expect(screen.queryByTestId("scope-control")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /every agent/i })).not.toBeInTheDocument();
  });

  test("clicking Edit opens the edit form in a modal dialog", () => {
    mockAgentLoaded();

    renderAt();

    // No dialog until the Edit button is clicked.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /edit agent/i })).toBeInTheDocument();
  });

  test("the edit form renames first, then PATCHes the agent's own fields", async () => {
    // The name is a LABEL now, so the form lets the user change it — and a
    // rename is the kind-agnostic `PATCH /resources/{uid}` every kind renames
    // through, not the agent kind's own PATCH. Both are addressed to the uid,
    // and the rename goes first: it is the one write that can be refused for a
    // reason the user has to fix, and a refusal must leave the rest unapplied.
    mockAgentLoaded();
    const order: string[] = [];
    const renameAsync = vi.fn(async () => {
      order.push("rename");
    });
    const patchAsync = vi.fn(async () => {
      order.push("patch");
    });
    vi.mocked(resourceHooks.useRenameResource).mockReturnValue({
      mutateAsync: renameAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof resourceHooks.useRenameResource>);
    vi.mocked(hooks.usePatchAgent).mockReturnValue({
      mutateAsync: patchAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.usePatchAgent>);

    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "renamed" } });
    fireEvent.change(within(dialog).getByLabelText("Description"), {
      target: { value: "the one I use" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /^save$/i }));

    expect(renameAsync).toHaveBeenCalledWith({ kind: "agent", uid: "u-cur", name: "renamed" });
    // The second write only goes out once the rename has resolved, so it is
    // awaited rather than asserted on the same tick.
    await waitFor(() =>
      expect(patchAsync).toHaveBeenCalledWith({
        uid: "u-cur",
        body: { description: "the one I use" },
      }),
    );
    expect(order).toEqual(["rename", "patch"]);
  });

  test("an unchanged name is not sent as a rename", async () => {
    // Every save would otherwise carry a rename to the name the agent already
    // has — a write with nothing to write, and a 409 waiting to happen the day
    // the daemon starts treating "taken by me" as taken.
    mockAgentLoaded();
    const renameAsync = vi.fn().mockResolvedValue({});
    const patchAsync = vi.fn().mockResolvedValue({});
    vi.mocked(resourceHooks.useRenameResource).mockReturnValue({
      mutateAsync: renameAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof resourceHooks.useRenameResource>);
    vi.mocked(hooks.usePatchAgent).mockReturnValue({
      mutateAsync: patchAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof hooks.usePatchAgent>);

    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Description"), {
      target: { value: "only this changed" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(patchAsync).toHaveBeenCalledWith({
        uid: "u-cur",
        body: { description: "only this changed" },
      }),
    );
    expect(renameAsync).not.toHaveBeenCalled();
  });

  test("?tab= opens that tab, so returning from a row's page keeps your place", () => {
    // Memory and Conversations rows open their own detail pages; the back link
    // on those pages carries ?tab= so the reader lands where they left rather
    // than on Overview.
    mockAgentLoaded();

    renderAt("/agents/u-cur?tab=conversations");

    expect(screen.getByRole("tab", { name: /conversations/i })).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(screen.getByRole("tab", { name: /overview/i })).toHaveAttribute(
      "data-state",
      "inactive",
    );
  });

  test("shows a not-found message when the agent fails to load", () => {
    useAgentMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: { code: "RESOURCE_NOT_FOUND", message: "nope" },
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useAgent>);

    renderAt();
    expect(screen.getByText(/failed to load agents/i)).toBeInTheDocument();
  });
});
