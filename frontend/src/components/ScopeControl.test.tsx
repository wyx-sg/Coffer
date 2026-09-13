// frontend/src/components/ScopeControl.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ScopeControl } from "./ScopeControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useScope", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useScope")>()),
  useResourceScope: vi.fn(),
  useUpdateResourceScope: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
}));

const scopeHooks = await import("@/lib/hooks/useScope");
const agentHooks = await import("@/lib/hooks/useAgents");
const machineHooks = await import("@/lib/hooks/useMachines");
const resourceHooks = await import("@/lib/hooks/useResourceMutations");

const mutate = vi.fn();
const enableMutate = vi.fn();
const disableMutate = vi.fn();

const LOCAL_ID = "a3f21c9e4b7d2610";
const OTHER_ID = "bb11cc22dd33ee44";

/** Two registered machines: this one, and one the user also owns. */
const MACHINES = [
  { machine_id: LOCAL_ID, name: "laptop", is_self: true },
  { machine_id: OTHER_ID, name: "desktop", is_self: false },
];

function seed(opts: {
  scope: Scope | null;
  supports_scope?: boolean;
  agents?: { name: string }[];
  machines?: typeof MACHINES;
}) {
  const {
    scope,
    supports_scope = true,
    agents = [{ name: "claude" }, { name: "codex" }],
    machines = MACHINES,
  } = opts;
  vi.mocked(scopeHooks.useResourceScope).mockReturnValue({
    data: { scope, supports_scope },
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useResourceScope>);
  vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
  vi.mocked(machineHooks.useMachines).mockReturnValue({
    data: { machines },
  } as unknown as ReturnType<typeof machineHooks.useMachines>);
  vi.mocked(resourceHooks.useEnableResource).mockReturnValue({
    mutate: enableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof resourceHooks.useEnableResource>);
  vi.mocked(resourceHooks.useDisableResource).mockReturnValue({
    mutate: disableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof resourceHooks.useDisableResource>);
}

const only = (agents: string[] | null, machines: string[] | null = null): Scope => ({
  agents,
  machines,
});

/** Close the picker, which is when the staged selection is written. */
function closeList() {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
}

function openList() {
  fireEvent.click(screen.getByRole("button", { name: /restricted/i }));
}

const segment = (label: RegExp) => screen.getByRole("button", { name: label });

afterEach(() => vi.clearAllMocks());

describe("ScopeControl", () => {
  test("everywhere marks that segment active and hides the pick-lists", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    expect(segment(/everywhere/i)).toHaveAttribute("aria-pressed", "true");
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/restricted/i)).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("switching everywhere -> restricted opens the lists and PUTs on close", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    // Opening stages nothing on the server — the dormant hint describes the
    // staged selection, not a write that already happened.
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closeList();
    expect(mutate).toHaveBeenCalledWith(only([]));
  });

  test("switching restricted -> everywhere PUTs null", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    fireEvent.click(segment(/everywhere/i));
    expect(mutate).toHaveBeenCalledWith(null);
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("checking an agent adds it to the agent axis alone", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    closeList();
    expect(mutate).toHaveBeenCalledWith(only(["claude", "codex"]));
  });

  test("the machine axis is a pick-list of the registry, never free text", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    // Unrestricted to start with, so the rows only appear once "every machine"
    // is unticked — and then they are checkboxes, not an input.
    fireEvent.click(screen.getByRole("checkbox", { name: /every machine/i }));
    const row = within(screen.getByTestId(`scope-machine-${OTHER_ID}`));
    expect(row.getByText("desktop")).toBeInTheDocument();
    expect(row.getByRole("checkbox")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("scope-machine-axis")).queryByRole("textbox"),
    ).not.toBeInTheDocument();
  });

  test("selecting a machine writes the derived id, not the display name", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every machine/i }));
    fireEvent.click(within(screen.getByTestId(`scope-machine-${OTHER_ID}`)).getByRole("checkbox"));
    closeList();
    expect(mutate).toHaveBeenCalledWith(only(["claude"], [OTHER_ID]));
  });

  test("the local machine's row is marked as this machine", () => {
    seed({ scope: only(null, [LOCAL_ID]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(
      within(screen.getByTestId(`scope-machine-${LOCAL_ID}`)).getByText(/this machine/i),
    ).toBeInTheDocument();
  });

  test("a machine axis that excludes this machine says so", () => {
    seed({ scope: only(null, [OTHER_ID]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/inactive on this machine/i)).toBeInTheDocument();
  });

  test("the machine axis is reported in preference to the agent axis", () => {
    // Both axes exclude this session. The API reports the machine axis first,
    // and so must the UI: a resource dormant on the whole machine is a
    // different thing to explain.
    seed({ scope: only(["ghost"], [OTHER_ID]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/inactive on this machine/i)).toBeInTheDocument();
    expect(screen.queryByText(/names no agent registered/i)).not.toBeInTheDocument();
  });

  test("an agent axis naming nobody registered here is explained as the agent axis", () => {
    seed({ scope: only(["ghost"], [LOCAL_ID]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/names no agent registered/i)).toBeInTheDocument();
  });

  test("a scope that excludes nothing raises no note", () => {
    seed({ scope: only(["claude"], [LOCAL_ID]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.queryByText(/inactive/i)).not.toBeInTheDocument();
  });

  test("a scoped-in agent that is not registered here renders with an unknown hint", () => {
    seed({ scope: only(["ghost"]), agents: [{ name: "claude" }] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
  });

  test("a machine id in scope that the registry does not hold is kept and badged", () => {
    seed({ scope: only(null, ["deadbeefdeadbeef"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    const row = within(screen.getByTestId("scope-machine-deadbeefdeadbeef"));
    expect(row.getByText(/not in the registry/i)).toBeInTheDocument();
  });

  test("unticking every-agent stages an empty agent axis and warns it is dormant", () => {
    seed({ scope: only(null, [LOCAL_ID]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every agent/i }));
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closeList();
    expect(mutate).toHaveBeenCalledWith(only([], [LOCAL_ID]));
  });

  test("a restricted scope relaxed to both axes unrestricted normalises to null", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every agent/i }));
    closeList();
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("shows the empty hint when no agent is registered and none is scoped", () => {
    seed({ scope: only([]), agents: [] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("shows the empty hint when the registry holds no machine", () => {
    seed({ scope: only(null, []), machines: [] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/no machines yet/i)).toBeInTheDocument();
  });

  test("a kind that declares no scope still gets a working enable/disable", () => {
    // Every kind Coffer ships today declares scope; this is the fallback for
    // one that does not, so the control never has to be forked for it.
    seed({ scope: null, supports_scope: false });
    render(<ScopeControl kind="unscoped_kind" name="tg" enabled />);
    expect(screen.queryByRole("button", { name: /everywhere/i })).not.toBeInTheDocument();
    expect(segment(/^enabled$/i)).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(segment(/^disabled$/i));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "unscoped_kind", name: "tg" });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("a disabled resource renders with the first segment active", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled={false} />);
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "true");
    // Scope survives the disable, but neither scope segment claims to be live.
    expect(segment(/restricted/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/everywhere/i)).toHaveAttribute("aria-pressed", "false");
  });

  test("clicking Disabled disables the resource and leaves the scope alone", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    fireEvent.click(segment(/^disabled$/i));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "fs" });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("everywhere on a disabled resource both enables it and clears the scope", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled={false} />);
    fireEvent.click(segment(/everywhere/i));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "fs" });
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("restricted on a disabled resource enables on close, without rewriting the scope", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled={false} />);
    openList();
    // Nothing yet: a write here would refetch the list and move the row the
    // open panel is anchored to.
    expect(enableMutate).not.toHaveBeenCalled();
    closeList();
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "fs" });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("a pre-fetched scope is used verbatim and switches the query off", () => {
    // The list tables pass the scope they already have; the control must not
    // add a GET per row. `enabled` is the hook's third argument.
    seed({ scope: null });
    render(<ScopeControl kind="skill" name="writing" enabled scope={only(["codex"])} />);

    expect(vi.mocked(scopeHooks.useResourceScope)).toHaveBeenCalledWith("skill", "writing", false);
    expect(segment(/restricted/i)).toHaveAttribute("aria-pressed", "true");
    expect(segment(/everywhere/i)).toHaveAttribute("aria-pressed", "false");
    openList();
    expect(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox")).toBeChecked();
  });

  test("a pre-fetched null scope still means everywhere", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="skill" name="writing" enabled scope={null} />);
    expect(segment(/everywhere/i)).toHaveAttribute("aria-pressed", "true");
  });

  test("every segment goes inert while a write is in flight", () => {
    seed({ scope: null });
    vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
      mutate,
      isPending: true,
    } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    expect(segment(/^disabled$/i)).toBeDisabled();
    expect(segment(/everywhere/i)).toBeDisabled();
    expect(segment(/restricted/i)).toBeDisabled();
  });
});

describe("the selection commits when the popover closes", () => {
  afterEach(() => vi.clearAllMocks());

  test("opening the lists writes nothing", () => {
    // Clicking the segment used to PUT straight away. That refetched the
    // resource list under an open popover, and the row it is anchored to moved
    // — so the panel appeared under a different row.
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" name="fs" enabled scope={null} />);
    openList();
    expect(mutate).not.toHaveBeenCalled();
  });

  test("ticking two agents writes once, when the popover closes", () => {
    seed({ scope: only([]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled scope={only([])} />);
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-claude")).getByRole("checkbox"));
    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    expect(mutate).not.toHaveBeenCalled();

    closeList();
    // One write carrying the whole selection, not one per tick.
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith(only(["claude", "codex"]));
  });

  test("closing an untouched list of the same selection writes nothing", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled scope={only(["claude"])} />);
    openList();
    closeList();
    expect(mutate).not.toHaveBeenCalled();
  });
});
