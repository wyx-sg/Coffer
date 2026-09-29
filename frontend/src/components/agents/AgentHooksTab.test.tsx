// frontend/src/components/agents/AgentHooksTab.test.tsx
//
// The read-only Hooks tab (spec agent-registry "List every hook in the agent's
// native config"): hooks grouped by event with matcher / command / source,
// Coffer's own row badged, the health line for Coffer's hook with Repair when it
// is out of date (Repair = Connect to Coffer), parse errors as a warning, and
// an empty state. Only the network boundary (`agentsApi`) is mocked.
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgentHooksTab } from "./AgentHooksTab";
import type { AgentHooksOut, AgentOut, CofferHook, NativeHook } from "@/lib/api/agents";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: { hooks: vi.fn(), connect: vi.fn(), disconnect: vi.fn() },
}));
const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);

const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude-code",
  type: "claude_code",
  config_dir: "/home/u/.claude",
  display_name: "Claude Code",
  model: null,
  fast_model: null,
  wire_api: null,
  version: null,
  state: "installed_active",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

const SETTINGS = "/home/u/.claude/settings.json";
const COFFER_CMD = "coffer memory deliver --agent-uid u-cc";

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

const COFFER_HOOK: CofferHook = {
  event: "SessionStart",
  path: SETTINGS,
  health: "current",
  trust: "not_required",
  installed_command: COFFER_CMD,
  expected_command: COFFER_CMD,
  last_fired_at: null,
};

function renderTab(data: AgentHooksOut) {
  api.hooks.mockResolvedValue(data);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<AgentHooksTab agent={AGENT} />, { wrapper: Wrapper });
}

afterEach(() => vi.clearAllMocks());

describe("AgentHooksTab", () => {
  test("groups hooks by event with matcher, command and source", async () => {
    renderTab({
      items: [
        hook({ event: "PreToolUse", matcher: "Bash", command: "./guard.sh" }),
        hook({ event: "SessionStart", command: COFFER_CMD, coffer: true }),
        hook({
          event: "PreToolUse",
          command: "hud --tick",
          source: "plugin",
          plugin: "claude-hud@market",
          path: "/home/u/.claude/plugins/hud/hooks.json",
        }),
      ],
      coffer_hook: COFFER_HOOK,
      parse_errors: [],
    });

    const pre = await screen.findByRole("list", { name: "PreToolUse" });
    const preRows = within(pre).getAllByRole("listitem");
    expect(preRows).toHaveLength(2);
    expect(within(preRows[0]).getByText("Bash")).toBeInTheDocument();
    expect(within(preRows[0]).getByText("./guard.sh")).toBeInTheDocument();
    expect(within(preRows[0]).getByText("User")).toBeInTheDocument();
    // No matcher reads "all"; a plugin row names its plugin.
    expect(within(preRows[1]).getByText("all")).toBeInTheDocument();
    expect(within(preRows[1]).getByText("Plugin claude-hud@market")).toBeInTheDocument();
    // Foreign hooks are not editable — only open / reveal their file.
    expect(within(preRows[0]).getByRole("button", { name: /open in editor/i })).toBeInTheDocument();

    // Coffer's own row carries the badge; the others do not.
    const start = screen.getByRole("list", { name: "SessionStart" });
    expect(within(start).getByText("Coffer")).toBeInTheDocument();
    expect(within(pre).queryByText("Coffer")).not.toBeInTheDocument();
  });

  test("a current Coffer hook shows its health and offers no Repair", async () => {
    renderTab({ items: [], coffer_hook: COFFER_HOOK, parse_errors: [] });
    expect(await screen.findByText("Current")).toBeInTheDocument();
    expect(screen.getByText(/never fired/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /repair/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/approval/i)).not.toBeInTheDocument();
  });

  test("a current hook Codex has not approved says so, and offers no Repair", async () => {
    renderTab({
      items: [],
      coffer_hook: { ...COFFER_HOOK, trust: "untrusted" },
      parse_errors: [],
    });
    expect(await screen.findByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Needs approval in Codex")).toBeInTheDocument();
    // Approving is the user's act in Codex: Coffer offers nothing to click.
    expect(screen.queryByRole("button", { name: /repair/i })).not.toBeInTheDocument();
  });

  test("a stale Coffer hook reads out of date, and Repair connects the agent", async () => {
    api.connect.mockResolvedValue({ state: "connected", parts: [] } as never);
    renderTab({
      items: [],
      coffer_hook: {
        ...COFFER_HOOK,
        health: "stale",
        installed_command: "coffer memory deliver --agent claude-code",
        last_fired_at: "2026-09-20T08:00:00Z",
      },
      parse_errors: [],
    });
    expect(await screen.findByText("Out of date")).toBeInTheDocument();
    expect(screen.getByText(/last fired 2026-09-20/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /repair/i }));
    await waitFor(() => expect(api.connect).toHaveBeenCalledWith("u-cc"));
  });

  test("no hooks at all shows the empty state, and parse errors a warning", async () => {
    renderTab({
      items: [],
      coffer_hook: null,
      parse_errors: [{ source: "settings", path: SETTINGS, error: "bad json" }],
    });
    expect(await screen.findByText("No hooks")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("bad json");
    // No Coffer hook for this type → no health line.
    expect(screen.queryByText("Coffer's hook")).not.toBeInTheDocument();
  });
});
