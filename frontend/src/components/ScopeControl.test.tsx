// frontend/src/components/ScopeControl.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ScopeControl } from "./ScopeControl";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useScope", () => ({
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

/** Open the agent list, which lives behind the "Selected agents" segment. */
function openList() {
  fireEvent.click(screen.getByRole("button", { name: /selected agents/i }));
}

const segment = (label: RegExp) => screen.getByRole("button", { name: label });

afterEach(() => vi.clearAllMocks());

describe("ScopeControl", () => {
  test("every-agent mode marks that segment active and hides the agent list", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    expect(segment(/every agent/i)).toHaveAttribute("aria-pressed", "true");
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/selected agents/i)).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("switching every-agent -> selected PUTs an empty list and opens the list", () => {
    seed({ scope: null });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(mutate).toHaveBeenCalledWith([]);
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
  });

  test("switching selected -> every-agent PUTs null", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    fireEvent.click(segment(/every agent/i));
    expect(mutate).toHaveBeenCalledWith(null);
    expect(enableMutate).not.toHaveBeenCalled();
  });

  test("the selected segment carries the count and is the active one", () => {
    seed({ scope: ["claude", "codex"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    const seg = segment(/selected agents \(2\)/i);
    expect(seg).toHaveAttribute("aria-pressed", "true");
  });

  test("clicking the already-active selected segment only toggles the list", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox", { name: "claude" })).toBeInTheDocument();
  });

  test("dormant warning renders for an empty selection", () => {
    seed({ scope: [] });
    render(<ScopeControl kind="skill" name="writing" enabled />);
    openList();
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
  });

  test("no dormant warning once at least one agent is selected", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="skill" name="writing" enabled />);
    openList();
    expect(screen.queryByText(/dormant/i)).not.toBeInTheDocument();
  });

  test("checking an agent adds it to the list", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: "codex" }));
    expect(mutate).toHaveBeenCalledWith(["claude", "codex"]);
  });

  test("unchecking the last agent PUTs an empty list", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: "claude" }));
    expect(mutate).toHaveBeenCalledWith([]);
  });

  test("an agent registered here but not selected renders unchecked", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByRole("checkbox", { name: "claude" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "codex" })).not.toBeChecked();
  });

  test("a scoped-in agent that is not registered here renders with an unknown hint", () => {
    seed({ scope: ["ghost"], agents: [{ name: "claude" }] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
  });

  test("selecting an agent preserves unregistered names already in scope", () => {
    seed({ scope: ["ghost"], agents: [{ name: "claude" }] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    fireEvent.click(screen.getByRole("checkbox", { name: "claude" }));
    expect(mutate).toHaveBeenCalledWith(["ghost", "claude"]);
  });

  test("shows the empty hint when no agent is registered and none is scoped", () => {
    seed({ scope: [], agents: [] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    openList();
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("a kind that declares no scope still gets a working enable/disable", () => {
    seed({ scope: null, supports_scope: false });
    render(<ScopeControl kind="channel" name="tg" enabled />);
    expect(screen.queryByRole("button", { name: /every agent/i })).not.toBeInTheDocument();
    expect(segment(/^enabled$/i)).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(segment(/^disabled$/i));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "channel", name: "tg" });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("a disabled resource renders with the first segment active", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled={false} />);
    expect(segment(/^disabled$/i)).toHaveAttribute("aria-pressed", "true");
    // Scope survives the disable, but neither scope segment claims to be live.
    expect(segment(/selected agents \(1\)/i)).toHaveAttribute("aria-pressed", "false");
    expect(segment(/every agent/i)).toHaveAttribute("aria-pressed", "false");
  });

  test("clicking Disabled disables the resource and leaves the scope alone", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    fireEvent.click(segment(/^disabled$/i));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "fs" });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("every-agent on a disabled resource both enables it and clears the scope", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled={false} />);
    fireEvent.click(segment(/every agent/i));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "fs" });
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("selected agents on a disabled resource enables without rewriting the scope", () => {
    seed({ scope: ["claude"] });
    render(<ScopeControl kind="mcp_server" name="fs" enabled={false} />);
    openList();
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "fs" });
    expect(mutate).not.toHaveBeenCalled();
  });

  test("every segment goes inert while a write is in flight", () => {
    seed({ scope: null });
    vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
      mutate,
      isPending: true,
    } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
    render(<ScopeControl kind="mcp_server" name="fs" enabled />);
    expect(segment(/^disabled$/i)).toBeDisabled();
    expect(segment(/every agent/i)).toBeDisabled();
    expect(segment(/selected agents/i)).toBeDisabled();
  });
});
