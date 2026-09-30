// src/components/agents/AgentHooksTab.test.tsx — the agent's Hooks tab, one table of every hook it runs.
//
// Spec agent-registry "List every hook in the agent's native config": each
// declared hook is a row with its event, command, file and matcher, owned by
// Coffer when it carries Coffer's marker; Coffer's own row reads its health,
// Codex's trust and its last fire, and offers Repair when out of date or
// missing. Only the network boundary (`agentsApi`) and the fs transport are mocked.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentHooksTab } from "./AgentHooksTab";
import en from "@/i18n/locales/en.json";
import type { AgentHooksOut, AgentOut, CofferHook, NativeHook } from "@/lib/api/agents";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({ agentsApi: { hooks: vi.fn() } }));
const openMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: vi.fn(() => Promise.resolve()) }),
}));
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
    wire_api: null,
    version: null,
    state: "installed_active",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

const SETTINGS = "/home/u/.claude/settings.json";
const LOCAL = "/home/u/.claude/settings.local.json";
const PLUGIN_HOOKS = "/home/u/.claude/plugins/cache/superpowers/hooks/hooks.json";
const COFFER_CMD = 'coffer memory hook --agent-uid u-claude_code --cwd "$PWD"';

function hook(over: Partial<NativeHook>): NativeHook {
  return {
    event: "PreToolUse",
    matcher: null,
    command: "echo hi",
    type: "command",
    timeout: null,
    source: "user",
    path: SETTINGS,
    plugin: null,
    coffer: false,
    ...over,
  };
}

const COFFER: CofferHook = {
  event: "SessionStart",
  path: SETTINGS,
  health: "current",
  trust: "not_required",
  installed_command: COFFER_CMD,
  expected_command: COFFER_CMD,
  last_fired_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
};
const COFFER_ROW = hook({ event: "SessionStart", command: COFFER_CMD, coffer: true });
const OWN_ROWS = [
  hook({ matcher: "Bash", command: "~/.claude/hooks/block-destructive.sh" }),
  hook({ event: "Stop", command: "afplay Glass.aiff", path: LOCAL }),
  hook({
    matcher: "Edit|Write",
    command: "${CLAUDE_PLUGIN_ROOT}/hooks/check-secrets.sh",
    source: "plugin",
    plugin: "superpowers@superpowers-marketplace",
    path: PLUGIN_HOOKS,
  }),
];

function Search() {
  return <div data-testid="search">{useLocation().search}</div>;
}

function renderTab(
  data: AgentHooksOut,
  opts: { type?: AgentOut["type"]; onRepair?: () => void; path?: string } = {},
) {
  api.hooks.mockResolvedValue(data);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[opts.path ?? "/agents/x/hooks"]}>
        <Routes>
          <Route
            path="/agents/x/hooks"
            element={
              <>
                {children}
                <Search />
              </>
            }
          />
          <Route path="/activity" element={<div data-testid="activity" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(
    <AgentHooksTab agent={agent(opts.type ?? "claude_code")} onRepair={opts.onRepair} />,
    {
      wrapper: Wrapper,
    },
  );
}

const rowOf = async (text: string) => (await screen.findByText(text)).closest("tr") as HTMLElement;

afterEach(() => vi.clearAllMocks());

describe("AgentHooksTab", () => {
  acceptance("agent-registry", "list an agent's hooks with Coffer's own marked", async () => {
    renderTab({ items: [COFFER_ROW, ...OWN_ROWS], coffer_hook: COFFER, parse_errors: [] });

    expect(
      await screen.findByText("4 hooks in 3 files · 1 is Coffer’s · 3 the agent’s own"),
    ).toBeInTheDocument();
    // Coffer's row: owned by Coffer, current, with its last fire.
    const coffer = await rowOf(COFFER_CMD);
    expect(within(coffer).getByText("SessionStart")).toBeInTheDocument();
    expect(within(coffer).getByText("Coffer’s")).toBeInTheDocument();
    expect(within(coffer).getByText("Current")).toBeInTheDocument();
    expect(within(coffer).getByText(/^fired 2 hours ago$/)).toBeInTheDocument();
    expect(within(coffer).getByText("~/.claude/settings.json")).toBeInTheDocument();
    expect(within(coffer).getByText("matcher Any")).toBeInTheDocument();
    // The agent's own: Active, no invented fire time; a plugin's hook names its plugin.
    const own = await rowOf("~/.claude/hooks/block-destructive.sh");
    expect(within(own).getByText("Active")).toBeInTheDocument();
    expect(within(own).getByText("The agent’s own")).toBeInTheDocument();
    expect(within(own).getByText("matcher Bash")).toBeInTheDocument();
    expect(within(own).queryByText(/fired/)).not.toBeInTheDocument();
    expect(
      within(await rowOf("${CLAUDE_PLUGIN_ROOT}/hooks/check-secrets.sh")).getByText(
        "superpowers · hooks.json",
      ),
    ).toBeInTheDocument();
    // A current hook offers no Repair.
    expect(screen.queryByRole("button", { name: /repair/i })).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Every hook in Claude Code’s own config, read-only. Change one in its file; only Coffer’s own hook is looked after here.",
      ),
    ).toBeInTheDocument();
  });

  acceptance(
    "agent-registry",
    "coffer's memory hook is one row with a chip per event",
    async () => {
      const cofferEntries = (
        [
          ["UserPromptSubmit", null],
          ["SessionStart", null],
          ["PreToolUse", "Bash"],
          ["PostToolUse", "Bash"],
        ] as const
      ).map(([event, matcher]) => hook({ event, matcher, command: COFFER_CMD, coffer: true }));
      renderTab({
        items: [...cofferEntries, ...OWN_ROWS],
        coffer_hook: { ...COFFER, event: "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit" },
        parse_errors: [],
      });

      expect(
        await screen.findByText("4 hooks in 3 files · 1 is Coffer’s · 3 the agent’s own"),
      ).toBeInTheDocument();
      // One row for all four entries, never the events joined into one string.
      expect(screen.getAllByText(COFFER_CMD)).toHaveLength(1);
      const row = await rowOf(COFFER_CMD);
      expect(within(row).getByText("Memory hook · 4 events")).toBeInTheDocument();
      for (const event of ["PostToolUse", "PreToolUse", "SessionStart", "UserPromptSubmit"]) {
        expect(within(row).getByText(event)).toBeInTheDocument();
      }
      expect(within(row).getByText("matcher Bash")).toBeInTheDocument();
      expect(screen.queryByText(/PostToolUse,PreToolUse/)).not.toBeInTheDocument();
    },
  );

  test("a missing Coffer hook lists its events as chips too", async () => {
    renderTab({
      items: [],
      coffer_hook: {
        ...COFFER,
        health: "missing",
        event: "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit",
      },
      parse_errors: [],
    });
    const row = await rowOf(en.agents.hooksTab.missing.title);
    expect(within(row).getByText("Memory hook · 4 events")).toBeInTheDocument();
    expect(within(row).getByText("UserPromptSubmit")).toBeInTheDocument();
    expect(screen.queryByText(/PostToolUse,PreToolUse/)).not.toBeInTheDocument();
  });

  acceptance("agent-registry", "report a stale Coffer hook", async () => {
    const onRepair = vi.fn();
    renderTab(
      {
        items: [{ ...COFFER_ROW, command: "coffer memory context --agent codex" }],
        coffer_hook: { ...COFFER, health: "stale", installed_command: "old" },
        parse_errors: [],
      },
      { onRepair },
    );
    const row = await rowOf("coffer memory context --agent codex");
    expect(await within(row).findByText("Out of date")).toBeInTheDocument();
    expect(within(row).getByText(/^fired /)).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "Repair Coffer’s memory hook" }));
    expect(onRepair).toHaveBeenCalledTimes(1);
  });

  test("a missing Coffer hook gets its own row with Repair, and no Open file", async () => {
    const onRepair = vi.fn();
    renderTab(
      {
        items: [hook({ path: "/home/u/.codex/hooks.json", matcher: "shell" })],
        coffer_hook: { ...COFFER, path: "/home/u/.codex/hooks.json", health: "missing" },
        parse_errors: [],
      },
      { type: "codex", onRepair },
    );
    expect(
      await screen.findByText("1 hook in 1 file · Coffer’s hook missing · 1 the agent’s own"),
    ).toBeInTheDocument();
    const row = await rowOf(en.agents.hooksTab.missing.title);
    expect(
      within(row).getByText(
        "Taken out of ~/.codex/hooks.json, so Codex starts sessions without memory.",
      ),
    ).toBeInTheDocument();
    expect(within(row).getByText("Missing")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /open/i })).not.toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: /repair/i }));
    expect(onRepair).toHaveBeenCalled();
  });

  test("Repair is not offered when the page gives the tab no way to run it", async () => {
    renderTab({ items: [], coffer_hook: { ...COFFER, health: "missing" }, parse_errors: [] });
    await screen.findByText(en.agents.hooksTab.missing.title);
    expect(screen.queryByRole("button", { name: /repair/i })).not.toBeInTheDocument();
  });

  test("an untrusted Codex hook says Codex will not run it until trusted", async () => {
    renderTab(
      { items: [COFFER_ROW], coffer_hook: { ...COFFER, trust: "untrusted" }, parse_errors: [] },
      { type: "codex" },
    );
    const row = await rowOf(COFFER_CMD);
    expect(await within(row).findByText("Untrusted")).toBeInTheDocument();
    expect(within(row).getByText("not approved in Codex")).toBeInTheDocument();
    expect(within(row).getByText("Codex hasn’t approved this hook")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Copy /hooks" })).toBeInTheDocument();
  });

  test.each([
    ["modified", "Changed since trusted"],
    ["disabled", "Turned off in Codex"],
  ] as const)("trust %s reads %s", async (trust, word) => {
    renderTab(
      { items: [COFFER_ROW], coffer_hook: { ...COFFER, trust }, parse_errors: [] },
      { type: "codex" },
    );
    expect(await within(await rowOf(COFFER_CMD)).findByText(word)).toBeInTheDocument();
  });

  test("a hook that never fired explains why, re-reads and opens Activity", async () => {
    renderTab(
      { items: [COFFER_ROW], coffer_hook: { ...COFFER, last_fired_at: null }, parse_errors: [] },
      { type: "codex" },
    );
    const row = await rowOf(COFFER_CMD);
    expect(await within(row).findByText("Never fired")).toBeInTheDocument();
    expect(within(row).getByText(en.agents.hooksTab.neverFired.title)).toBeInTheDocument();
    expect(
      within(row).getByText(/this Codex build doesn’t load ~\/\.claude\/settings\.json/),
    ).toBeInTheDocument();

    fireEvent.click(within(row).getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.hooks).toHaveBeenCalledTimes(2));
    fireEvent.click(within(row).getByRole("button", { name: "Open Activity" }));
    expect(await screen.findByTestId("activity")).toBeInTheDocument();
  });

  test("Open file opens the declaring file in the editor", async () => {
    renderTab({ items: OWN_ROWS, coffer_hook: null, parse_errors: [] });
    fireEvent.click(await screen.findByRole("button", { name: `Open ${LOCAL}` }));
    await waitFor(() => expect(openMock).toHaveBeenCalledWith(LOCAL, expect.anything()));
  });

  // Scenario (revise-web-ui-ia, agent-registry): "the owner filter narrows an installed-kind tab"
  test("the owner filter narrows the table to Coffer's hook and keeps it in the URL", async () => {
    renderTab({ items: [COFFER_ROW, ...OWN_ROWS], coffer_hook: COFFER, parse_errors: [] });
    await screen.findByText(COFFER_CMD);
    fireEvent.click(screen.getByRole("radio", { name: "Coffer’s" }));
    expect(screen.getByTestId("search")).toHaveTextContent("?owner=coffer");
    expect(screen.getByText(COFFER_CMD)).toBeInTheDocument();
    expect(screen.queryByText("afplay Glass.aiff")).not.toBeInTheDocument();
  });

  test("search narrows by command", async () => {
    renderTab({ items: [COFFER_ROW, ...OWN_ROWS], coffer_hook: COFFER, parse_errors: [] });
    await screen.findByText(COFFER_CMD);
    fireEvent.change(screen.getByLabelText("Search hooks"), {
      target: { value: "afplay" },
    });
    expect(screen.getByText("afplay Glass.aiff")).toBeInTheDocument();
    expect(screen.queryByText(COFFER_CMD)).not.toBeInTheDocument();
  });

  test("a file that does not parse is a warning naming it, beside the other hooks", async () => {
    renderTab({
      items: [OWN_ROWS[0]],
      coffer_hook: null,
      parse_errors: [{ source: "settings.local.json", path: LOCAL, error: "bad json" }],
    });
    expect(
      await screen.findByText("Couldn’t read ~/.claude/settings.local.json: bad json"),
    ).toBeInTheDocument();
    expect(screen.getByText("~/.claude/hooks/block-destructive.sh")).toBeInTheDocument();
  });

  test("an agent with no hooks shows the empty state naming it", async () => {
    renderTab({ items: [], coffer_hook: null, parse_errors: [] }, { type: "codex" });
    expect(await screen.findByText("Codex has no hooks")).toBeInTheDocument();
  });
});
