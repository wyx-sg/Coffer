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

function seed(opts: {
  scope: Scope | null;
  supports_scope?: boolean;
  agents?: { name: string }[];
}) {
  const { scope, supports_scope = true, agents = [{ name: "claude" }, { name: "codex" }] } = opts;
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

const only = (agents: string[] | null): Scope => ({ agents });

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
  test("everywhere marks that segment active and hides the pick-list", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    expect(segment(/everywhere/i)).toHaveAttribute("aria-pressed", "true");
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/restricted/i)).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("switching everywhere -> restricted opens the list and PUTs on close", () => {
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

  test("checking an agent adds it to the stored selection", () => {
    seed({ scope: only(["claude"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(within(screen.getByTestId("scope-agent-codex")).getByRole("checkbox"));
    closeList();
    expect(mutate).toHaveBeenCalledWith(only(["claude", "codex"]));
  });

  test("a scope naming nobody registered here is explained on the trigger and in the panel", () => {
    seed({ scope: only(["ghost"]) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/names no agent registered/i)).toBeInTheDocument();
  });

  test("a scope that excludes nothing raises no note", () => {
    seed({ scope: only(["claude"]) });
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

  test("unticking every-agent stages an empty agent list and warns it is dormant", () => {
    seed({ scope: only(null) });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: /every agent/i }));
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    closeList();
    expect(mutate).toHaveBeenCalledWith(only([]));
  });

  test("a restricted scope relaxed to every agent normalises to null", () => {
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

  test("opening the list writes nothing", () => {
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
