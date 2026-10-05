// frontend/src/components/ScopeControl.test.tsx
//
// The single-resource half of the reach control: which mode is live, what each
// choice writes, that every change is written at once (in order), and that a
// failed write stays in the popover on the agent's row.
//
// Everything the control SENDS is keyed on the resource's uid and on agent
// uids; everything the user READS is a name. The fixtures keep the two
// deliberately unalike.
import { afterEach, describe, expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { ScopeControl } from "./ScopeControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/hooks/useScope", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useScope")>()),
  useResourceScope: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const { resourcesApi } = await import("@/lib/api/resources");
const { scopeApi } = await import("@/lib/api/scope");
const scopeHooks = await import("@/lib/hooks/useScope");
const agentHooks = await import("@/lib/hooks/useAgents");
const enable = vi.mocked(resourcesApi.enable);
const disable = vi.mocked(resourcesApi.disable);
const put = vi.mocked(scopeApi.put);

const FS_UID = "u-mcp-9f2c";
const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";
const GHOST = "u-agent-0000";
const AGENTS = [
  { uid: CLAUDE, name: "claude", type: "claude_code" },
  { uid: CODEX, name: "codex", type: "codex" },
];

const only = (agents: string[] | null): Scope => ({ agents });

let qc: QueryClient;
function mount(props: { enabled?: boolean; scope?: Scope | null; fetched?: Scope | null } = {}) {
  const { enabled = true, scope, fetched = null } = props;
  vi.mocked(scopeHooks.useResourceScope).mockReturnValue({
    data: { scope: fetched, supports_scope: true },
  } as unknown as ReturnType<typeof scopeHooks.useResourceScope>);
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: AGENTS,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ScopeControl kind="mcp_server" uid={FS_UID} enabled={enabled} scope={scope} />
    </QueryClientProvider>,
  );
}

const trigger = () => within(screen.getByTestId("scope-control")).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });
const tick = (name: string) =>
  fireEvent.click(within(screen.getByTestId(`scope-agent-${name}`)).getByRole("checkbox"));
const closePanel = () =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

afterEach(() => {
  vi.clearAllMocks();
  vi.mocked(enable).mockResolvedValue(undefined as never);
  vi.mocked(disable).mockResolvedValue(undefined as never);
  vi.mocked(put).mockResolvedValue(undefined as never);
});
// Re-arm once for the first test too.
enable.mockResolvedValue(undefined as never);
disable.mockResolvedValue(undefined as never);
put.mockResolvedValue(undefined as never);

describe("the live mode", () => {
  test("a fetched null scope reads All agents, with no request beyond the scope query", () => {
    mount({ fetched: null });
    expect(trigger()).toHaveTextContent(/^All agents$/);
  });

  test("a pre-fetched scope is used verbatim and switches the query off", () => {
    mount({ scope: only([CODEX]) });
    expect(scopeHooks.useResourceScope).toHaveBeenCalledWith(FS_UID, false);
    expect(trigger().querySelectorAll("[data-agent-mark]")).toHaveLength(1);
  });

  test("a disabled resource reads Off and carries no amber note for its scope", () => {
    mount({ enabled: false, scope: only([GHOST]) });
    expect(trigger()).toHaveTextContent(/^Off$/);
    expect(trigger()).not.toHaveClass("text-warning");
  });

  test("an enabled resource naming no registered agent is flagged", () => {
    mount({ scope: only([GHOST]) });
    expect(trigger()).toHaveClass("text-warning");
  });

  test("a scope naming a registered agent raises no note", () => {
    mount({ scope: only([CLAUDE]) });
    expect(trigger()).not.toHaveClass("text-warning");
  });
});

describe("each change writes at once", () => {
  test("Off posts disable and writes no scope", async () => {
    mount({ scope: only([CLAUDE]) });
    openPanel();
    fireEvent.click(choice(/^off$/i));
    await waitFor(() => expect(disable).toHaveBeenCalledWith(FS_UID));
    expect(put).not.toHaveBeenCalled();
    expect(enable).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved"));
  });

  test("All agents on a disabled resource enables it and clears the scope", async () => {
    mount({ enabled: false, scope: only([CLAUDE]) });
    openPanel();
    fireEvent.click(choice(/^all agents$/i));
    await waitFor(() => expect(put).toHaveBeenCalledWith(FS_UID, null));
    expect(enable).toHaveBeenCalledWith(FS_UID);
  });

  test("All agents on an already-everywhere resource skips the redundant write", async () => {
    mount({ enabled: false, scope: null });
    openPanel();
    fireEvent.click(choice(/^all agents$/i));
    await waitFor(() => expect(enable).toHaveBeenCalled());
    expect(put).not.toHaveBeenCalled();
  });

  test("Chosen agents on a disabled resource enables it and keeps the ticks as they were", async () => {
    mount({ enabled: false, scope: only([CODEX]) });
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    await waitFor(() => expect(enable).toHaveBeenCalledWith(FS_UID));
    // The stored scope already is the remembered list: nothing to rewrite.
    expect(put).not.toHaveBeenCalled();
  });

  test("every tick is its own write, in order, with the whole list", async () => {
    mount({ scope: null });
    openPanel();
    tick("claude");
    tick("codex");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls.map((c) => c[1])).toEqual([only([CLAUDE]), only([CLAUDE, CODEX])]);
    expect(enable).not.toHaveBeenCalled();
  });

  test("a switch to Chosen agents with nothing ticked writes nothing until the first tick", async () => {
    mount({ scope: null });
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    expect(choice(/chosen agents/i)).toBeChecked();
    expect(put).not.toHaveBeenCalled();
    expect(disable).not.toHaveBeenCalled();
    tick("claude");
    await waitFor(() => expect(put).toHaveBeenCalledWith(FS_UID, only([CLAUDE])));
  });

  test("the last ticked agent cannot be unticked; the panel says to turn it off", async () => {
    mount({ scope: only([CLAUDE]) });
    openPanel();
    expect(screen.getByRole("checkbox", { name: /claude/i })).toBeDisabled();
    expect(screen.getByTestId("scope-keep-one")).toHaveTextContent(/turn it off/i);
    tick("codex");
    await waitFor(() => expect(put).toHaveBeenCalledWith(FS_UID, only([CLAUDE, CODEX])));
    expect(screen.queryByTestId("scope-keep-one")).toBeNull();
  });

  test("the trigger shows what was just written before any refetch", async () => {
    mount({ scope: null });
    openPanel();
    fireEvent.click(choice(/chosen agents/i));
    tick("codex");
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(trigger().querySelectorAll("[data-agent-mark]")).toHaveLength(1);
  });

  test("opening and closing an untouched panel writes nothing", () => {
    mount({ scope: only([CLAUDE]) });
    openPanel();
    closePanel();
    expect(disable).not.toHaveBeenCalled();
    expect(enable).not.toHaveBeenCalled();
    expect(put).not.toHaveBeenCalled();
  });
});

describe("the lists refresh once, when the panel closes", () => {
  test("no refetch while the popover is open", async () => {
    mount({ scope: null });
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    openPanel();
    tick("claude");
    await waitFor(() => expect(put).toHaveBeenCalled());
    await screen.findByText(/Saved/);
    expect(invalidate).not.toHaveBeenCalled();
    closePanel();
    await waitFor(() => expect(invalidate).toHaveBeenCalled());
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["resources"]));
  });
});

describe("a failed write stays in the popover", () => {
  test("the ticked agent's row says Failed with Retry and Untick; no toast", async () => {
    mount({ scope: only([CLAUDE]) });
    put.mockRejectedValueOnce(new ApiError("RESOURCE_NOT_FOUND", "permission denied"));
    openPanel();
    tick("codex");
    const row = within(await screen.findByTestId("scope-agent-codex"));
    await waitFor(() => expect(row.getByText("Failed")).toBeInTheDocument());
    // The other agent's row is untouched.
    expect(within(screen.getByTestId("scope-agent-claude")).queryByText("Failed")).toBeNull();

    // Retry resends exactly that write.
    fireEvent.click(row.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1][1]).toEqual(only([CLAUDE, CODEX]));
    await waitFor(() => expect(screen.queryByText("Failed")).toBeNull());
  });

  test("Untick writes the list without that agent and clears the failure", async () => {
    mount({ scope: only([CLAUDE]) });
    put.mockRejectedValueOnce(new ApiError("RESOURCE_NOT_FOUND", "permission denied"));
    openPanel();
    tick("codex");
    const row = within(await screen.findByTestId("scope-agent-codex"));
    await waitFor(() => expect(row.getByText("Failed")).toBeInTheDocument());
    fireEvent.click(row.getByRole("button", { name: /untick codex/i }));
    await waitFor(() => expect(screen.queryByText("Failed")).toBeNull());
    // Stored list already is [claude], so nothing more has to be written.
    expect(put).toHaveBeenCalledTimes(1);
  });
});

describe("a scope saved but not delivered to one agent (skills, canvas 4.3.09)", () => {
  test("that agent's row says Failed with the reason; Retry sends the scope again, Untick drops the agent", async () => {
    mount({ scope: only([CLAUDE]) });
    put.mockResolvedValueOnce({
      delivery: [
        { agent_uid: CLAUDE, agent_name: "claude", ok: true, reason: null },
        { agent_uid: CODEX, agent_name: "codex", ok: false, reason: "permission denied" },
      ],
    } as never);
    openPanel();
    tick("codex");
    const row = within(await screen.findByTestId("scope-agent-codex"));
    await waitFor(() => expect(row.getByText("Failed")).toBeInTheDocument());
    expect(row.getByText("permission denied")).toBeInTheDocument();
    // The agent that took it is untouched, and the scope itself was saved.
    expect(within(screen.getByTestId("scope-agent-claude")).queryByText("Failed")).toBeNull();
    expect(put.mock.calls[0][1]).toEqual(only([CLAUDE, CODEX]));

    // Retry resends the same scope even though the server already holds it.
    fireEvent.click(row.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1][1]).toEqual(only([CLAUDE, CODEX]));
    await waitFor(() => expect(screen.queryByText("Failed")).toBeNull());
  });

  test("Untick writes the list without that agent", async () => {
    mount({ scope: only([CLAUDE]) });
    put.mockResolvedValueOnce({
      delivery: [{ agent_uid: CODEX, agent_name: "codex", ok: false, reason: "permission denied" }],
    } as never);
    openPanel();
    tick("codex");
    const row = within(await screen.findByTestId("scope-agent-codex"));
    await waitFor(() => expect(row.getByText("Failed")).toBeInTheDocument());
    fireEvent.click(row.getByRole("button", { name: /untick codex/i }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1][1]).toEqual(only([CLAUDE]));
    await waitFor(() => expect(screen.queryByText("Failed")).toBeNull());
  });
});
