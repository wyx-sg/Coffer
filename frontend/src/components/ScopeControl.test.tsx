// frontend/src/components/ScopeControl.test.tsx
//
// The single-resource half of the reach control: which state is live, what
// each choice writes, and whether this resource reaches nobody *here*.
//
// Everything the control SENDS is keyed on the resource's uid and on agent
// uids; everything the user READS is a name. The fixtures below keep the two
// deliberately unalike — a uid equal to its name would let an assertion reach
// for the wrong field and still pass, which is exactly the confusion the uid
// exists to end.
import { afterEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";

import { ScopeControl } from "./ScopeControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useScope", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useScope")>()),
  useResourceScope: vi.fn(),
  useUpdateResourceScope: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
}));

const scopeHooks = await import("@/lib/hooks/useScope");
const agentHooks = await import("@/lib/hooks/useAgents");
const resourceHooks = await import("@/lib/hooks/useResourceMutations");

const mutate = vi.fn(() => Promise.resolve());
const enableMutate = vi.fn(() => Promise.resolve());
const disableMutate = vi.fn(() => Promise.resolve());
/** Let the queued writes settle. */
const settle = () => act(async () => {});

/** The resources under test: an identity, and separately a label. */
const FS_UID = "u-mcp-9f2c"; // named "fs"
const WRITING_UID = "u-skill-4e8d"; // named "writing"

/** The agents the machine knows, as the pair the picker works in: a uid a
 *  scope stores, and the name the row is labelled and asserted by. */
const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";
/** A uid in a stored scope that no registered agent answers to. */
const GHOST = "u-agent-0000";

const AGENTS = [
  { uid: CLAUDE, name: "claude" },
  { uid: CODEX, name: "codex" },
];

function seed(opts: { scope: Scope | null; agents?: { uid: string; name: string }[] }) {
  const { scope, agents = AGENTS } = opts;
  vi.mocked(scopeHooks.useResourceScope).mockReturnValue({
    data: { scope, supports_scope: true },
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useResourceScope>);
  vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
    mutateAsync: mutate,
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
  vi.mocked(resourceHooks.useEnableResource).mockReturnValue({
    mutateAsync: enableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof resourceHooks.useEnableResource>);
  vi.mocked(resourceHooks.useDisableResource).mockReturnValue({
    mutateAsync: disableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof resourceHooks.useDisableResource>);
}

/** A scope, as the wire spells it: agent UIDS, never names. */
const only = (agents: string[] | null): Scope => ({ agents });

/** The one button: its text is the reach, and clicking it opens the panel. */
const trigger = () => within(screen.getByTestId("scope-control")).getByRole("button");
const openPanel = () => fireEvent.click(trigger());
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });

/** One agent's row in the pick-list, found the way the DOM labels it — by the
 *  NAME the user reads, even though ticking it writes the uid. */
const agentRow = (name: string) => within(screen.getByTestId(`scope-agent-${name}`));

/** Open the panel and switch to Chosen agents. */
function openPicker() {
  openPanel();
  fireEvent.click(choice(/chosen agents/i));
}

afterEach(() => vi.clearAllMocks());

const FS = { kind: "mcp_server", uid: FS_UID };

describe("ScopeControl", () => {
  test("everywhere reads as All agents, with no panel open", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveTextContent(/^all agents$/i);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("the control is mounted quiet: failures are shown in the panel, not toasted", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(vi.mocked(scopeHooks.useUpdateResourceScope)).toHaveBeenCalledWith(
      "mcp_server",
      FS_UID,
      {
        quiet: true,
      },
    );
  });

  test("All agents -> Chosen agents writes the empty list at once", async () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPicker();
    await settle();
    expect(mutate).toHaveBeenCalledWith(only([]));
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("Chosen agents -> All agents PUTs null", async () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(choice(/all agents/i));
    await settle();
    expect(mutate).toHaveBeenCalledWith(null);
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("ticking an agent adds its uid to the stored selection, at once", async () => {
    // The row is found by name and the write carries the uid: that is the
    // whole translation this picker performs.
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    await settle();
    expect(mutate).toHaveBeenCalledWith(only([CLAUDE, CODEX]));
  });

  test("a scope naming nobody registered here is explained on the button and in the panel", () => {
    // The button would otherwise show a badge for an agent that is not here and
    // look healthy while reaching nobody on this machine, so the note colours it.
    seed({ scope: only([GHOST]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveAttribute("title", expect.stringMatching(/names no agent added/i));
    expect(trigger().className).toContain("text-warning");
    openPanel();
    expect(screen.getByText(/names no agent added/i)).toBeInTheDocument();
  });

  test("an empty list reads No agent in muted grey, with no amber note", () => {
    seed({ scope: only([]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveTextContent(/^no agent$/i);
    expect(trigger().className).not.toContain("text-warning");
  });

  test("a scope that excludes nothing raises no note", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger().className).not.toContain("text-warning");
    openPanel();
    expect(screen.queryByText(/inactive/i)).not.toBeInTheDocument();
  });

  test("a scoped-in agent uid that is not added here renders with an unknown hint", () => {
    seed({ scope: only([GHOST]), agents: [{ uid: CLAUDE, name: "claude" }] });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    const row = agentRow(GHOST);
    expect(row.getByText(GHOST)).toBeInTheDocument();
    expect(row.getByText(/not added/i)).toBeInTheDocument();
  });

  test("a stored scope spelling all-agents the long way reads as All agents", () => {
    seed({ scope: only(null) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveTextContent(/^all agents$/i);
    openPanel();
    expect(choice(/all agents/i)).toBeChecked();
  });

  test("shows the empty hint when no agent is registered and none is scoped", () => {
    seed({ scope: only([]), agents: [] });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    expect(screen.getByText(/no agents added/i)).toBeInTheDocument();
  });

  test("an Off resource says so, and keeps its ticks without claiming a scope is live", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    expect(trigger()).toHaveTextContent(/^off/i);
    openPanel();
    expect(choice(/^off$/i)).toBeChecked();
    expect(choice(/chosen agents/i)).not.toBeChecked();
    expect(choice(/all agents/i)).not.toBeChecked();
    expect(agentRow("claude").getByRole("checkbox")).toBeChecked();
    expect(agentRow("claude").getByRole("checkbox")).toBeDisabled();
  });

  test("an Off resource is not also flagged for the scope underneath it", () => {
    seed({ scope: only([GHOST]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    expect(trigger()).toHaveTextContent(/^off/i);
    expect(trigger().className).not.toContain("text-warning");
  });

  test("an ENABLED resource reaching nobody here is still flagged", () => {
    seed({ scope: only([GHOST]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger().className).toContain("text-warning");
  });

  test("choosing Off disables the resource and leaves the scope alone", async () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(choice(/^off$/i));
    await settle();
    expect(disableMutate).toHaveBeenCalledWith(FS);
    expect(mutate).not.toHaveBeenCalled();
  });

  test("All agents on an Off resource both enables it and clears the scope", async () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    openPanel();
    fireEvent.click(choice(/all agents/i));
    await settle();
    expect(enableMutate).toHaveBeenCalledWith(FS);
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("Chosen agents on an Off resource enables it and keeps the stored list (no rewrite)", async () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    openPicker();
    await settle();
    expect(enableMutate).toHaveBeenCalledWith(FS);
    expect(mutate).not.toHaveBeenCalled();
  });

  test("a pre-fetched scope is used verbatim and switches the query off", () => {
    // The list tables pass the scope they already have; the control must not
    // add a GET per row. The query takes the uid and an `enabled` flag — no
    // kind — so `false` is the second argument.
    seed({ scope: null });
    render(<ScopeControl kind="skill" uid={WRITING_UID} enabled scope={only([CODEX])} />);

    expect(vi.mocked(scopeHooks.useResourceScope)).toHaveBeenCalledWith(WRITING_UID, false);
    openPanel();
    expect(choice(/chosen agents/i)).toBeChecked();
    expect(agentRow("codex").getByRole("checkbox")).toBeChecked();
  });

  test("a pre-fetched null scope still means All agents", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="skill" uid={WRITING_UID} enabled scope={null} />);
    expect(trigger()).toHaveTextContent(/^all agents$/i);
  });

  test("the resource's name is shown under the panel title", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled resourceName="fs" />);
    openPanel();
    expect(screen.getByText("fs")).toBeInTheDocument();
  });

  test("a rejected write shows its reason and a Retry in the panel", async () => {
    seed({ scope: only([]) });
    mutate.mockRejectedValueOnce(new Error("backend down"));
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={only([])} />);
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    await settle();
    expect(screen.getByTestId("scope-agent-failed")).toHaveTextContent("Failed — backend down");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await settle();
    expect(mutate).toHaveBeenCalledTimes(2);
    expect(mutate).toHaveBeenLastCalledWith(only([CLAUDE]));
  });
});

describe("every change is written as it is made", () => {
  afterEach(() => vi.clearAllMocks());

  test("opening the panel writes nothing", async () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={null} />);
    openPanel();
    await settle();
    expect(mutate).not.toHaveBeenCalled();
    expect(disableMutate).not.toHaveBeenCalled();
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("ticking two agents writes twice, each the whole list", async () => {
    seed({ scope: only([]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={only([])} />);
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    await settle();
    expect(mutate).toHaveBeenCalledTimes(2);
    expect(mutate).toHaveBeenNthCalledWith(1, only([CLAUDE]));
    expect(mutate).toHaveBeenNthCalledWith(2, only([CLAUDE, CODEX]));
  });

  test("closing an untouched panel writes nothing", async () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={only([CLAUDE])} />);
    openPanel();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await settle();
    expect(mutate).not.toHaveBeenCalled();
    expect(disableMutate).not.toHaveBeenCalled();
  });
});
