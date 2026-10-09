// src/components/agents/AgentHooksTab.test.tsx — the agent's Hooks tab: the agent's own hooks.
//
// Spec agent-registry "List every hook in the agent's native config": the
// agent's own hooks are one table with search and an Event filter, and a row
// opens a read-only details dialog. Coffer installs no hook of its own, so the
// tab has no Coffer block. Only the network boundary (`agentsApi`) is mocked.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentHooksTab } from "./AgentHooksTab";
import { fsApi } from "@/lib/api/fs";
import type { AgentHooksOut, AgentOut, NativeHook } from "@/lib/api/agents";

vi.mock("@/lib/api/agents", () => ({ agentsApi: { hooks: vi.fn() } }));
vi.mock("@/lib/api/fs", () => ({ fsApi: { open: vi.fn(), reveal: vi.fn() } }));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

function agent(type: AgentOut["type"]): AgentOut {
  return {
    uid: `u-${type}`,
    name: type,
    type,
    config_dir: type === "codex" ? "/home/u/.codex" : "/home/u/.claude",
    display_name: type === "codex" ? "Codex" : "Claude Code",
    model: null,
    tier_models: null,
    version: null,
    install_handoff: null,
    connection_uid: null,
    state: "installed_active",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

const SETTINGS = "/home/u/.claude/settings.json";
const LOCAL = "/home/u/.claude/settings.local.json";
const PLUGIN_HOOKS = "/home/u/.claude/plugins/cache/superpowers/hooks/hooks.json";

function hook(over: Partial<NativeHook>): NativeHook {
  return {
    event: "PreToolUse",
    matcher: null,
    command: "echo hi",
    type: "command",
    timeout: null,
    group_index: 0,
    hook_index: 0,
    source: "user",
    path: SETTINGS,
    plugin: null,
    ...over,
  };
}

const OWN_ROWS = [
  hook({ event: "UserPromptSubmit", command: "~/.claude/hooks/ticket-context.sh", path: LOCAL }),
  hook({
    matcher: "Bash",
    command: "~/.claude/hooks/block-destructive.sh",
    timeout: 60,
    group_index: 0,
    hook_index: 1,
  }),
  hook({
    matcher: "Edit|Write",
    command: "${CLAUDE_PLUGIN_ROOT}/hooks/check-secrets.sh",
    source: "plugin",
    plugin: "superpowers@superpowers-marketplace",
    path: PLUGIN_HOOKS,
  }),
  hook({ event: "Stop", command: "afplay Glass.aiff" }),
];

function Where() {
  const { pathname, search } = useLocation();
  return <div data-testid="where">{pathname + search}</div>;
}

function renderTab(data: AgentHooksOut, opts: { type?: AgentOut["type"] } = {}) {
  api.hooks.mockResolvedValue(data);
  vi.mocked(fsApi.open).mockResolvedValue(undefined);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/agents/x/hooks"]}>
        <Routes>
          <Route
            path="/agents/x/hooks"
            element={
              <>
                {children}
                <Where />
              </>
            }
          />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(<AgentHooksTab agent={agent(opts.type ?? "claude_code")} />, { wrapper: Wrapper });
}

const full = (): AgentHooksOut => ({ items: OWN_ROWS, parse_errors: [] });
const ownBlock = async () => within(await screen.findByTestId("own-hooks-section"));

afterEach(() => vi.clearAllMocks());

describe("AgentHooksTab", () => {
  test("lists the agent's own hooks in one table", async () => {
    renderTab(full());

    // The agent's own hooks: one table, with no Coffer block above it.
    const own = await ownBlock();
    expect(
      own.getByText(
        "4 hooks in 3 files, from Claude Code’s own config. Click one for its details.",
      ),
    ).toBeInTheDocument();
    expect(own.getAllByRole("row")).toHaveLength(1 + OWN_ROWS.length);
    expect(own.getByText("~/.claude/hooks/block-destructive.sh")).toBeInTheDocument();
    expect(own.getByText("superpowers · hooks.json")).toBeInTheDocument();
    expect(own.getAllByText("Any")).toHaveLength(2);
  });

  test("the tab has no Coffer hook block and no Repair", async () => {
    renderTab(full());
    await ownBlock();
    expect(screen.queryByTestId("coffer-hook-section")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Repair" })).not.toBeInTheDocument();
    expect(screen.queryByText(/memory hook/i)).not.toBeInTheDocument();
  });

  test("search narrows by command or file and says how many of how many show", async () => {
    renderTab(full());
    const own = await ownBlock();
    await own.findByText("afplay Glass.aiff");
    fireEvent.change(own.getByLabelText("Search command or file"), { target: { value: "afplay" } });
    expect(own.getByText("afplay Glass.aiff")).toBeInTheDocument();
    expect(own.queryByText("~/.claude/hooks/block-destructive.sh")).not.toBeInTheDocument();
    expect(own.getByText("Showing 1 of 4")).toBeInTheDocument();
    fireEvent.change(own.getByLabelText("Search command or file"), { target: { value: "zzz" } });
    expect(own.getByText("No hooks match.")).toBeInTheDocument();
  });

  test("the Event filter lists the six events with counts and narrows the table", async () => {
    renderTab(full());
    const own = await ownBlock();
    await own.findByText("afplay Glass.aiff");
    fireEvent.click(own.getByRole("button", { name: "Filter by event" }));
    const list = within(await screen.findByRole("listbox"));
    expect(list.getAllByRole("option")).toHaveLength(7);
    expect(list.getByRole("option", { name: /^All events\s*4$/ })).toBeInTheDocument();
    expect(list.getByRole("option", { name: /^SessionStart\s*0$/ })).toBeInTheDocument();
    expect(list.getByRole("option", { name: /^PreToolUse\s*2$/ })).toBeInTheDocument();
    fireEvent.click(list.getByRole("option", { name: /^PreToolUse/ }));
    expect(own.getAllByRole("row")).toHaveLength(1 + 2);
    expect(own.getByText("Showing 2 of 4")).toBeInTheDocument();
  });

  test("a row opens read-only details: command, matcher, timeout, file and JSON position", async () => {
    renderTab(full());
    const own = await ownBlock();
    fireEvent.click(await own.findByText("~/.claude/hooks/block-destructive.sh"));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("PreToolUse hook")).toBeInTheDocument();
    expect(dialog.getByText("Before a tool call. It can block the call.")).toBeInTheDocument();
    expect(dialog.getByText("Bash")).toBeInTheDocument();
    expect(dialog.getByText("Shell command")).toBeInTheDocument();
    expect(dialog.getByText("60 s")).toBeInTheDocument();
    expect(dialog.getByText("hooks.PreToolUse[0].hooks[1]")).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Open in editor" }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(SETTINGS, undefined));
  });

  test("a hook with no matcher reads Any tool, and a plugin's hook file opens in the editor too", async () => {
    renderTab(full());
    const own = await ownBlock();
    fireEvent.click(await own.findByText("afplay Glass.aiff"));
    expect(within(await screen.findByRole("dialog")).getByText("Any tool")).toBeInTheDocument();
    fireEvent.click(
      within(screen.getByRole("dialog")).getAllByRole("button", { name: "Close" })[0],
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    fireEvent.click(own.getByText("${CLAUDE_PLUGIN_ROOT}/hooks/check-secrets.sh"));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.click(dialog.getByRole("button", { name: "Open in editor" }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(PLUGIN_HOOKS, undefined));
  });

  test("a file that does not parse is a warning naming it, beside the other hooks", async () => {
    renderTab({
      items: [OWN_ROWS[1]],
      parse_errors: [{ source: "settings.local.json", path: LOCAL, error: "bad json" }],
    });
    expect(
      await screen.findByText("Couldn’t read ~/.claude/settings.local.json: bad json"),
    ).toBeInTheDocument();
    expect(screen.getByText("~/.claude/hooks/block-destructive.sh")).toBeInTheDocument();
  });

  test("an agent with no hooks of its own says so inside its section", async () => {
    renderTab({ items: [], parse_errors: [] }, { type: "codex" });
    expect(await screen.findByText("Codex has no hooks of its own")).toBeInTheDocument();
  });
});
