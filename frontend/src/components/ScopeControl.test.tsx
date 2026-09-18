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
import { fireEvent, render, screen, within } from "@testing-library/react";

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

const mutate = vi.fn();
const enableMutate = vi.fn();
const disableMutate = vi.fn();

/** The resources under test: an identity, and separately a label. */
const FS_UID = "u-mcp-9f2c"; // named "fs"
const WRITING_UID = "u-skill-4e8d"; // named "writing"
const TG_UID = "u-channel-1b77"; // named "tg"

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

function seed(opts: {
  scope: Scope | null;
  supports_scope?: boolean;
  agents?: { uid: string; name: string }[];
}) {
  const { scope, supports_scope = true, agents = AGENTS } = opts;
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
  vi.mocked(resourceHooks.useEnableResource).mockReturnValue({
    mutate: enableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof resourceHooks.useEnableResource>);
  vi.mocked(resourceHooks.useDisableResource).mockReturnValue({
    mutate: disableMutate,
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

/** Dismiss the panel, which is when the staged choice is written. */
function closePanel() {
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
}

/** Open the panel and land on the pick-list, which is the only choice that
 *  leaves it open. */
function openPicker() {
  openPanel();
  fireEvent.click(choice(/only selected agents/i));
}

afterEach(() => vi.clearAllMocks());

describe("ScopeControl", () => {
  test("everywhere reads as every agent, with no panel open", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveTextContent(/every agent/i);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("switching everywhere -> only selected opens the list and PUTs on close", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPicker();
    // Picking the list stages nothing on the server — the dormant hint
    // describes the staged selection, not a write that already happened.
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closePanel();
    expect(mutate).toHaveBeenCalledWith(only([]));
  });

  test("switching only-selected -> every agent PUTs null", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(choice(/every agent/i));
    expect(mutate).toHaveBeenCalledWith(null);
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("checking an agent adds its uid to the stored selection", () => {
    // The row is found by name and the write carries the uid: that is the
    // whole translation this picker performs.
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    closePanel();
    expect(mutate).toHaveBeenCalledWith(only([CLAUDE, CODEX]));
  });

  test("a scope naming nobody registered here is explained on the button and in the panel", () => {
    // The button would otherwise read "1 agent" and look perfectly healthy
    // while reaching nobody on this machine, so the note colours it too.
    seed({ scope: only([GHOST]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveAttribute("title", expect.stringMatching(/names no agent registered/i));
    expect(trigger().className).toContain("status-warn");
    openPanel();
    expect(screen.getByText(/names no agent registered/i)).toBeInTheDocument();
  });

  test("a scope that excludes nothing raises no note", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger().className).not.toContain("status-warn");
    openPanel();
    expect(screen.queryByText(/inactive/i)).not.toBeInTheDocument();
  });

  test("a scoped-in agent uid that is not registered here renders with an unknown hint", () => {
    // There is no name to print for it, so it prints as itself. Dropping the
    // row would silently widen the scope the user is looking at.
    seed({ scope: only([GHOST]), agents: [{ uid: CLAUDE, name: "claude" }] });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    const row = agentRow(GHOST);
    expect(row.getByText(GHOST)).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
  });

  test("a stored scope spelling every-agent the long way reads as every agent", () => {
    // `{agents: null}` and `null` are one state; the button and the panel must
    // not disagree about which.
    seed({ scope: only(null) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toHaveTextContent(/every agent/i);
    openPanel();
    expect(choice(/every agent/i)).toBeChecked();
  });

  test("narrowing from every agent stages an empty list and warns it is dormant", () => {
    seed({ scope: only(null) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPicker();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closePanel();
    expect(mutate).toHaveBeenCalledWith(only([]));
  });

  test("relaxing a restricted scope back to every agent writes null, not a full list", () => {
    // "Every agent" is its own choice with its own write, so the wire never
    // carries the same state under a second name.
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(choice(/every agent/i));
    expect(mutate).toHaveBeenCalledWith(null);
    expect(mutate).toHaveBeenCalledOnce();
  });

  test("shows the empty hint when no agent is registered and none is scoped", () => {
    seed({ scope: only([]), agents: [] });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("a kind that declares no scope still gets a working enable/disable", () => {
    // Every kind Coffer ships today declares scope; this is the fallback for
    // one that does not, so the control never has to be forked for it. It stays
    // ONE button so a table's status column reads the same whatever the kind.
    seed({ scope: null, supports_scope: false });
    render(<ScopeControl kind="unscoped_kind" uid={TG_UID} enabled />);
    expect(trigger()).toHaveTextContent(/^enabled/i);
    openPanel();
    expect(screen.queryByRole("radio", { name: /every agent/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    fireEvent.click(choice(/^disabled$/i));
    // `kind` rides along for the invalidation; the request is the uid's.
    expect(disableMutate).toHaveBeenCalledWith({ kind: "unscoped_kind", uid: TG_UID });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("a disabled resource says so, and no scope state claims to be live", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    expect(trigger()).toHaveTextContent(/^disabled/i);
    openPanel();
    expect(choice(/^disabled$/i)).toBeChecked();
    // Scope survives the disable, so the list it will come back to is visible —
    // but neither scope choice claims to be the live one.
    expect(choice(/only selected agents/i)).not.toBeChecked();
    expect(choice(/every agent/i)).not.toBeChecked();
    expect(agentRow("claude").getByRole("checkbox")).toBeChecked();
  });

  test("a disabled resource is not also flagged for the scope underneath it", () => {
    // Two rows both reading "Disabled" used to render in two colours, because
    // one of them had a scope naming nobody this machine knows. "Disabled" is
    // already the whole reason it reaches nobody, and the scope only starts
    // mattering once it is switched back on — so the warning is noise the
    // reader cannot act on, and an inconsistency in a column of identical
    // labels.
    seed({ scope: only([]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);

    expect(trigger()).toHaveTextContent(/^disabled/i);
    expect(trigger().className).not.toContain("status-warn");
    expect(screen.queryByText(/not active here/i)).toBeNull();
  });

  test("an ENABLED resource reaching nobody here is still flagged", () => {
    // The case the warning exists for: the button reads like a healthy scope
    // while the resource reaches no agent on this machine.
    seed({ scope: only([GHOST]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);

    expect(trigger().className).toContain("status-warn");
  });

  test("choosing Disabled disables the resource and leaves the scope alone", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    openPanel();
    fireEvent.click(choice(/^disabled$/i));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "mcp_server", uid: FS_UID });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("every agent on a disabled resource both enables it and clears the scope", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    openPanel();
    fireEvent.click(choice(/every agent/i));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", uid: FS_UID });
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("the pick-list on a disabled resource enables on close, without rewriting the scope", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} />);
    openPicker();
    // Nothing yet: a write here would refetch the list and move the row the
    // open panel is anchored to.
    expect(enableMutate).not.toHaveBeenCalled();
    closePanel();
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", uid: FS_UID });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("a pre-fetched scope is used verbatim and switches the query off", () => {
    // The list tables pass the scope they already have; the control must not
    // add a GET per row. The query takes the uid and an `enabled` flag — no
    // kind — so `false` is the second argument.
    seed({ scope: null });
    render(<ScopeControl kind="skill" uid={WRITING_UID} enabled scope={only([CODEX])} />);

    expect(vi.mocked(scopeHooks.useResourceScope)).toHaveBeenCalledWith(WRITING_UID, false);
    expect(trigger()).toHaveTextContent(/^1 agent/i);
    openPanel();
    expect(choice(/only selected agents/i)).toBeChecked();
    expect(agentRow("codex").getByRole("checkbox")).toBeChecked();
  });

  test("a pre-fetched null scope still means every agent", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="skill" uid={WRITING_UID} enabled scope={null} />);
    expect(trigger()).toHaveTextContent(/every agent/i);
  });

  test("the control goes inert while a write is in flight", () => {
    seed({ scope: null });
    vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
      mutate,
      isPending: true,
    } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled />);
    expect(trigger()).toBeDisabled();
  });
});

describe("the choice commits when the panel closes", () => {
  afterEach(() => vi.clearAllMocks());

  test("opening the panel writes nothing", () => {
    // Clicking a segment used to PUT straight away. That refetched the
    // resource list under an open popover, and the row it is anchored to moved
    // — so the panel appeared under a different row.
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={null} />);
    openPanel();
    expect(mutate).not.toHaveBeenCalled();
    expect(disableMutate).not.toHaveBeenCalled();
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("ticking two agents writes once, when the panel closes", () => {
    seed({ scope: only([]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={only([])} />);
    openPanel();
    fireEvent.click(agentRow("claude").getByRole("checkbox"));
    fireEvent.click(agentRow("codex").getByRole("checkbox"));
    expect(mutate).not.toHaveBeenCalled();

    closePanel();
    // One write carrying the whole selection, not one per tick.
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith(only([CLAUDE, CODEX]));
  });

  test("closing an untouched panel of the same selection writes nothing", () => {
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled scope={only([CLAUDE])} />);
    openPanel();
    closePanel();
    expect(mutate).not.toHaveBeenCalled();
  });

  test("closing an untouched panel on a DISABLED resource does not re-disable it", () => {
    // The one the consumer cannot dedupe: a disable has no "same value" to
    // compare against, so an untouched close would post one and write a real
    // audit event for a panel the user only glanced at.
    seed({ scope: only([CLAUDE]) });
    render(<ScopeControl kind="mcp_server" uid={FS_UID} enabled={false} scope={only([CLAUDE])} />);
    openPanel();
    closePanel();
    expect(disableMutate).not.toHaveBeenCalled();
    expect(enableMutate).not.toHaveBeenCalled();
    expect(mutate).not.toHaveBeenCalled();
  });
});
