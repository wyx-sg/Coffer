// src/components/agents/AgentHooksTab.test.tsx — the agent's Hooks tab: Coffer's memory hook, then the agent's own.
//
// Spec agent-registry "List every hook in the agent's native config": Coffer's
// hook is one block (state, command, event tags, file) whose fix sits at the
// title's right; the agent's own hooks are one table with search and an Event
// filter, and a row opens a read-only details dialog. Only the network boundary
// (`agentsApi`) is mocked.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentHooksTab } from "./AgentHooksTab";
import type { AgentHooksOut, AgentOut, CofferHook, NativeHook } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({ agentsApi: { hooks: vi.fn(), listConfigFiles: vi.fn() } }));
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
    effort: null,
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
const COFFER_CMD = "coffer memory index --agent-uid u-claude_code";

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
    coffer: false,
    ...over,
  };
}

const COFFER: CofferHook = {
  event: "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit",
  path: SETTINGS,
  health: "current",
  trust: "not_required",
  installed_command: COFFER_CMD,
  expected_command: COFFER_CMD,
  last_fired_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
};
const COFFER_ROWS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"].map(
  (event, i) => hook({ event, command: COFFER_CMD, coffer: true, group_index: i }),
);
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

function renderTab(
  data: AgentHooksOut,
  opts: { type?: AgentOut["type"]; onRepair?: () => void } = {},
) {
  api.hooks.mockResolvedValue(data);
  api.listConfigFiles.mockResolvedValue({
    items: [
      { key: "settings", path: SETTINGS },
      { key: "settings_local", path: LOCAL },
    ],
  } as never);
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
  return render(
    <AgentHooksTab agent={agent(opts.type ?? "claude_code")} onRepair={opts.onRepair} />,
    { wrapper: Wrapper },
  );
}

const full = (over: Partial<CofferHook> = {}): AgentHooksOut => ({
  items: [...COFFER_ROWS, ...OWN_ROWS],
  coffer_hook: { ...COFFER, ...over },
  parse_errors: [],
});
const cofferBlock = async () => within(await screen.findByTestId("coffer-hook-section"));
const ownBlock = async () => within(await screen.findByTestId("own-hooks-section"));

afterEach(() => vi.clearAllMocks());

describe("AgentHooksTab", () => {
  acceptance("agent-registry", "list an agent's hooks with Coffer's own marked", async () => {
    renderTab(full());

    // Coffer's hook: one block, events as tags, the file as a link, no fix when current.
    const coffer = await cofferBlock();
    expect(
      coffer.getByText("Gives every session Coffer’s memory. One hook on 4 events."),
    ).toBeInTheDocument();
    expect(coffer.getByText("Current")).toBeInTheDocument();
    expect(coffer.getByText(/^Fired /)).toBeInTheDocument();
    expect(coffer.getByText(COFFER_CMD)).toBeInTheDocument();
    for (const e of ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"]) {
      expect(coffer.getByText(e)).toBeInTheDocument();
    }
    expect(coffer.getByRole("link", { name: "~/.claude/settings.json" })).toHaveAttribute(
      "href",
      "/agents/claude_code/config?file=settings",
    );
    expect(coffer.queryByRole("button")).not.toBeInTheDocument();

    // The agent's own hooks: one table, Coffer's hook is not repeated in it.
    const own = await ownBlock();
    expect(
      own.getByText(
        "4 hooks in 3 files, from Claude Code’s own config. Click one for its details.",
      ),
    ).toBeInTheDocument();
    expect(own.getAllByRole("row")).toHaveLength(1 + OWN_ROWS.length);
    expect(own.queryByText(COFFER_CMD)).not.toBeInTheDocument();
    expect(own.getByText("~/.claude/hooks/block-destructive.sh")).toBeInTheDocument();
    expect(own.getByText("superpowers · hooks.json")).toBeInTheDocument();
    expect(own.getAllByText("Any")).toHaveLength(2);
  });

  acceptance(
    "agent-registry",
    "coffer's memory hook leads the Hooks tab and the agent's own follow",
    async () => {
      renderTab(full());
      const coffer = await cofferBlock();
      const own = await ownBlock();
      const first = screen.getByTestId("coffer-hook-section");
      const second = screen.getByTestId("own-hooks-section");
      expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(coffer.getByText(COFFER_CMD)).toBeInTheDocument();
      expect(own.queryByText(COFFER_CMD)).not.toBeInTheDocument();
      expect(own.getAllByRole("row")).toHaveLength(1 + OWN_ROWS.length);
      // A row opens a read-only dialog; searching narrows and says how many of how many.
      fireEvent.click(await own.findByText("~/.claude/hooks/block-destructive.sh"));
      const dialog = within(await screen.findByRole("dialog"));
      expect(dialog.getByText("hooks.PreToolUse[0].hooks[1]")).toBeInTheDocument();
      fireEvent.click(dialog.getAllByRole("button", { name: "Close" })[0]);
      fireEvent.change(own.getByLabelText("Search command or file"), {
        target: { value: "afplay" },
      });
      expect(own.getByText("Showing 1 of 4")).toBeInTheDocument();
    },
  );

  test("a stale Coffer hook says why and Repair opens the review flow", async () => {
    const onRepair = vi.fn();
    renderTab(full({ health: "stale", installed_command: "coffer memory index --agent old" }), {
      onRepair,
    });
    const coffer = await cofferBlock();
    expect(
      coffer.getByText(
        "Written by an older Coffer, so its command no longer works and sessions start without memory.",
      ),
    ).toBeInTheDocument();
    expect(coffer.getByText("Out of date")).toBeInTheDocument();
    fireEvent.click(coffer.getByRole("button", { name: "Repair" }));
    expect(onRepair).toHaveBeenCalledTimes(1);
  });

  test("a missing Coffer hook offers Repair, shows no command and still names its events", async () => {
    const onRepair = vi.fn();
    renderTab(
      {
        items: [hook({ path: "/home/u/.codex/hooks.json", matcher: "shell" })],
        coffer_hook: { ...COFFER, path: "/home/u/.codex/hooks.json", health: "missing" },
        parse_errors: [],
      },
      { type: "codex", onRepair },
    );
    const coffer = await cofferBlock();
    expect(coffer.getByText("Missing")).toBeInTheDocument();
    expect(
      coffer.getByText(/taken out of .*hooks\.json, so Codex starts sessions without memory/),
    ).toBeInTheDocument();
    expect(coffer.getByText("—")).toBeInTheDocument();
    expect(coffer.getByText("PostToolUse")).toBeInTheDocument();
    fireEvent.click(coffer.getByRole("button", { name: "Repair" }));
    expect(onRepair).toHaveBeenCalled();
  });

  test("Repair is not offered when the page gives the tab no way to run it", async () => {
    renderTab(full({ health: "missing" }));
    const coffer = await cofferBlock();
    expect(coffer.queryByRole("button", { name: "Repair" })).not.toBeInTheDocument();
  });

  test("a hook Codex has not approved reads Not approved and offers Check again", async () => {
    renderTab(full({ trust: "untrusted", last_fired_at: null }), { type: "codex" });
    const coffer = await cofferBlock();
    expect(coffer.getByText("Not approved")).toBeInTheDocument();
    expect(coffer.getByText("Never fired")).toBeInTheDocument();
    expect(coffer.getByText(/Codex skips hooks you haven’t approved/)).toBeInTheDocument();
    expect(coffer.queryByRole("button", { name: "Repair" })).not.toBeInTheDocument();
    fireEvent.click(coffer.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.hooks).toHaveBeenCalledTimes(2));
  });

  test("a hook whose command changed after approval reads Changed since trusted", async () => {
    renderTab(full({ trust: "modified" }), { type: "codex" });
    const coffer = await cofferBlock();
    expect(coffer.getByText("Changed since trusted")).toBeInTheDocument();
    expect(coffer.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });

  test("a hook that never fired gives the likely cause, Check again and a way to Activity", async () => {
    renderTab(full({ last_fired_at: null }), { type: "codex" });
    const coffer = await cofferBlock();
    expect(coffer.getByText("Never fired")).toBeInTheDocument();
    expect(coffer.getByText(/Likely cause: this Codex build doesn’t load/)).toBeInTheDocument();
    expect(coffer.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    fireEvent.click(coffer.getByRole("link", { name: "View in Activity" }));
    expect(await screen.findByText("/activity")).toBeInTheDocument();
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
    fireEvent.click(dialog.getByRole("button", { name: "Open in Config files" }));
    expect(await screen.findByText("/agents/claude_code/config?file=settings")).toBeInTheDocument();
  });

  test("a hook with no matcher reads Any tool, and a plugin's file has no Config files link", async () => {
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
    expect(dialog.queryByRole("button", { name: "Open in Config files" })).not.toBeInTheDocument();
  });

  test("a file that does not parse is a warning naming it, beside the other hooks", async () => {
    renderTab({
      items: [OWN_ROWS[1]],
      coffer_hook: null,
      parse_errors: [{ source: "settings.local.json", path: LOCAL, error: "bad json" }],
    });
    expect(
      await screen.findByText("Couldn’t read ~/.claude/settings.local.json: bad json"),
    ).toBeInTheDocument();
    expect(screen.getByText("~/.claude/hooks/block-destructive.sh")).toBeInTheDocument();
    expect(screen.queryByTestId("coffer-hook-section")).not.toBeInTheDocument();
  });

  test("an agent with no hooks of its own says so inside its section", async () => {
    renderTab({ items: [], coffer_hook: null, parse_errors: [] }, { type: "codex" });
    expect(await screen.findByText("Codex has no hooks of its own")).toBeInTheDocument();
  });
});
