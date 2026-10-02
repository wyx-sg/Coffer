// src/components/agents/AgentHooksTab.test.tsx — the agent's Hooks tab: every hook it runs, grouped by event.
//
// Spec agent-registry "List every hook in the agent's native config": each
// declared hook is listed under its event with its command, matcher and file,
// marked Coffer when it carries Coffer's marker; Coffer's own hook has its health,
// Codex's trust and its last fire said once in a status block, with Repair when
// out of date or missing. Only the network boundary (`agentsApi`) is mocked.
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

const eventOf = async (event: string) => within(await screen.findByTestId(`hook-event-${event}`));
const status = async () => within(await screen.findByTestId("coffer-hook-status"));

afterEach(() => vi.clearAllMocks());

describe("AgentHooksTab", () => {
  acceptance("agent-registry", "list an agent's hooks with Coffer's own marked", async () => {
    renderTab({ items: [COFFER_ROW, ...OWN_ROWS], coffer_hook: COFFER, parse_errors: [] });

    expect(
      await screen.findByText("4 hooks in 3 files · 1 is Coffer’s · 3 the agent’s own"),
    ).toBeInTheDocument();
    // Grouped by event: Coffer's hook under SessionStart, marked; a healthy one has no status block.
    const session = await eventOf("SessionStart");
    expect(session.getByText(COFFER_CMD)).toBeInTheDocument();
    expect(session.getByText("Coffer")).toBeInTheDocument();
    expect(session.getByText(/matcher Any/)).toBeInTheDocument();
    expect(session.getByText(/~\/\.claude\/settings\.json/)).toBeInTheDocument();
    expect(screen.queryByTestId("coffer-hook-status")).not.toBeInTheDocument();
    // The agent's own, with its matcher; a plugin's hook names its plugin.
    const pre = await eventOf("PreToolUse");
    expect(pre.getByText("~/.claude/hooks/block-destructive.sh")).toBeInTheDocument();
    expect(pre.getByText(/matcher Bash/)).toBeInTheDocument();
    expect(pre.queryByText("Coffer")).not.toBeInTheDocument();
    expect(pre.getByText(/superpowers · hooks\.json/)).toBeInTheDocument();
    expect((await eventOf("Stop")).getByText("afplay Glass.aiff")).toBeInTheDocument();
    // Events come in the order the agent fires them; no row opens a file.
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual(["SessionStart", "PreToolUse", "Stop"]);
    expect(screen.queryByRole("button", { name: /open/i })).not.toBeInTheDocument();
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
      // One hook, listed under each event it sits on — never the events joined into one string.
      for (const event of ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"]) {
        expect((await eventOf(event)).getByText(COFFER_CMD)).toBeInTheDocument();
      }
      expect(screen.getAllByText(COFFER_CMD)).toHaveLength(4);
      expect(screen.queryByText(/PostToolUse,PreToolUse/)).not.toBeInTheDocument();
    },
  );

  test("a missing Coffer hook is said once in the status block, not per event", async () => {
    renderTab({
      items: [],
      coffer_hook: {
        ...COFFER,
        health: "missing",
        event: "PostToolUse,PreToolUse,SessionStart,UserPromptSubmit",
      },
      parse_errors: [],
    });
    const block = await status();
    expect(block.getByText(en.agents.hooksTab.missing.title)).toBeInTheDocument();
    expect(block.getByText("Missing")).toBeInTheDocument();
    expect(screen.getAllByText(en.agents.hooksTab.missing.title)).toHaveLength(1);
  });

  acceptance("agent-registry", "report a stale Coffer hook", async () => {
    const onRepair = vi.fn();
    renderTab(
      {
        items: [{ ...COFFER_ROW, command: "coffer memory hook --agent-uid agt_stale" }],
        coffer_hook: { ...COFFER, health: "stale", installed_command: "old" },
        parse_errors: [],
      },
      { onRepair },
    );
    const block = await status();
    expect(await block.findByText("Out of date")).toBeInTheDocument();
    expect(block.getByText(/^fired /)).toBeInTheDocument();
    fireEvent.click(block.getByRole("button", { name: "Repair Coffer’s memory hook" }));
    expect(onRepair).toHaveBeenCalledTimes(1);
  });

  test("a missing Coffer hook offers Repair, and no Open file", async () => {
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
    const block = await status();
    expect(
      block.getByText("Taken out of ~/.codex/hooks.json, so Codex starts sessions without memory."),
    ).toBeInTheDocument();
    expect(block.getByText("Missing")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open/i })).not.toBeInTheDocument();
    fireEvent.click(block.getByRole("button", { name: /repair/i }));
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
    const block = await status();
    expect(await block.findByText("Untrusted")).toBeInTheDocument();
    expect(block.getByText("not approved in Codex")).toBeInTheDocument();
    expect(block.getByText("Codex hasn’t approved this hook")).toBeInTheDocument();
    expect(block.getByRole("button", { name: "Copy /hooks" })).toBeInTheDocument();
  });

  test.each([
    ["modified", "Changed since trusted"],
    ["disabled", "Turned off in Codex"],
  ] as const)("trust %s reads %s", async (trust, word) => {
    renderTab(
      { items: [COFFER_ROW], coffer_hook: { ...COFFER, trust }, parse_errors: [] },
      { type: "codex" },
    );
    expect(await (await status()).findByText(word)).toBeInTheDocument();
  });

  test("a hook that never fired explains why, re-reads and opens Activity", async () => {
    renderTab(
      { items: [COFFER_ROW], coffer_hook: { ...COFFER, last_fired_at: null }, parse_errors: [] },
      { type: "codex" },
    );
    const block = await status();
    expect(await block.findByText("Never fired")).toBeInTheDocument();
    expect(block.getByText(en.agents.hooksTab.neverFired.title)).toBeInTheDocument();
    expect(
      block.getByText(/this Codex build doesn’t load ~\/\.claude\/settings\.json/),
    ).toBeInTheDocument();

    fireEvent.click(block.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.hooks).toHaveBeenCalledTimes(2));
    fireEvent.click(block.getByRole("button", { name: "Open Activity" }));
    expect(await screen.findByTestId("activity")).toBeInTheDocument();
  });

  // Spec agent-registry "Filter an agent's installed kinds by owner" (the scenario itself is on the Skills tab).
  test("the owner filter narrows the list to Coffer's hook and keeps it in the URL", async () => {
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
