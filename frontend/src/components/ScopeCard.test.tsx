// frontend/src/components/ScopeCard.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ScopeCard } from "./ScopeCard";
import type { SyncMachine } from "@/lib/hooks/useMachines";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(),
  useUpdateResourceScope: vi.fn(),
}));
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const scopeHooks = await import("@/lib/hooks/useScope");
const machineHooks = await import("@/lib/hooks/useMachines");
const agentHooks = await import("@/lib/hooks/useAgents");

const LOCAL: SyncMachine = {
  machine_id: "M-LOCAL",
  display_name: "studio",
  platform: "darwin",
  os_version: null,
  coffer_version: null,
  last_sync_at: null,
  is_local: true,
};
const OTHER: SyncMachine = {
  ...LOCAL,
  machine_id: "M-OTHER",
  display_name: "laptop",
  is_local: false,
};

const mutate = vi.fn();

function seed(opts: {
  scope: Scope | null;
  axes: string[];
  machines?: SyncMachine[];
  agents?: { name: string }[];
}) {
  const { scope, axes, machines = [LOCAL, OTHER], agents = [] } = opts;
  vi.mocked(scopeHooks.useResourceScope).mockReturnValue({
    data: { scope, axes },
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useResourceScope>);
  vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
  vi.mocked(machineHooks.useMachines).mockReturnValue({
    data: { machines },
  } as unknown as ReturnType<typeof machineHooks.useMachines>);
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

afterEach(() => vi.clearAllMocks());

describe("ScopeCard", () => {
  test("everywhere mode shows no machine rows", () => {
    seed({ scope: null, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    expect(screen.getByRole("button", { name: /everywhere/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /custom/i })).toBeInTheDocument();
    expect(screen.queryByText("studio")).not.toBeInTheDocument();
  });

  test("switching Everywhere -> Custom pre-seeds known machines", () => {
    seed({ scope: null, axes: ["machine", "agent"] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("button", { name: /custom/i }));
    expect(mutate).toHaveBeenCalledWith({
      "M-LOCAL": "*",
      "M-OTHER": "*",
    });
  });

  test("switching Everywhere -> Custom with no machines PUTs {}", () => {
    seed({ scope: null, axes: ["machine"], machines: [] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("button", { name: /custom/i }));
    expect(mutate).toHaveBeenCalledWith({});
  });

  test("switching Custom -> Everywhere PUTs null", () => {
    seed({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    fireEvent.click(screen.getByRole("button", { name: /everywhere/i }));
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("dormant warning renders for custom scope with no entries", () => {
    seed({ scope: {}, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
  });

  test("no dormant warning once at least one machine is on", () => {
    seed({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    expect(screen.queryByText(/dormant/i)).not.toBeInTheDocument();
  });

  test("marks the local machine row with the this-machine badge", () => {
    seed({ scope: {}, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    const localRow = within(screen.getByTestId("scope-row-M-LOCAL"));
    expect(localRow.getByText(/this machine/i)).toBeInTheDocument();
    const otherRow = within(screen.getByTestId("scope-row-M-OTHER"));
    expect(otherRow.queryByText(/this machine/i)).not.toBeInTheDocument();
  });

  test("machine-only kind: toggling a row on PUTs { id: '*' }, no agent selectors", () => {
    seed({ scope: {}, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));
    fireEvent.click(row.getByRole("switch"));
    expect(mutate).toHaveBeenCalledWith({ "M-LOCAL": "*" });
    expect(screen.queryByText(/all agents/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("machine-only kind: toggling an on row off removes its entry", () => {
    seed({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));
    fireEvent.click(row.getByRole("switch"));
    expect(mutate).toHaveBeenCalledWith({});
  });

  test("dual-axis kind: turning a row on defaults to all agents ('*')", () => {
    seed({
      scope: {},
      axes: ["machine", "agent"],
      agents: [{ name: "claude" }, { name: "codex" }],
    });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));
    fireEvent.click(row.getByRole("switch"));
    expect(mutate).toHaveBeenCalledWith({ "M-LOCAL": "*" });
  });

  test("dual-axis kind: unchecking all-agents reveals per-agent checkboxes and PUTs []", () => {
    seed({
      scope: { "M-LOCAL": "*" },
      axes: ["machine", "agent"],
      agents: [{ name: "claude" }, { name: "codex" }],
    });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));
    const allAgents = row.getByRole("checkbox", { name: /all agents/i });
    expect(allAgents).toBeChecked();
    fireEvent.click(allAgents);
    expect(mutate).toHaveBeenCalledWith({ "M-LOCAL": [] });
  });

  test("dual-axis kind: per-agent checkbox toggling updates the agent list", () => {
    seed({
      scope: { "M-LOCAL": ["claude"] },
      axes: ["machine", "agent"],
      agents: [{ name: "claude" }, { name: "codex" }],
    });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));

    fireEvent.click(row.getByRole("checkbox", { name: "codex" }));
    expect(mutate).toHaveBeenCalledWith({ "M-LOCAL": ["claude", "codex"] });

    fireEvent.click(row.getByRole("checkbox", { name: "claude" }));
    expect(mutate).toHaveBeenCalledWith({ "M-LOCAL": [] });
  });

  test("dual-axis kind: checking all-agents PUTs '*'", () => {
    seed({
      scope: { "M-LOCAL": ["claude"] },
      axes: ["machine", "agent"],
      agents: [{ name: "claude" }],
    });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));
    fireEvent.click(row.getByRole("checkbox", { name: /all agents/i }));
    expect(mutate).toHaveBeenCalledWith({ "M-LOCAL": "*" });
  });

  test("machine-only kind renders no agent selectors even when a row is on", () => {
    seed({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });
    render(<ScopeCard kind="channel" name="tg" />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/all agents/i)).not.toBeInTheDocument();
  });

  test("unknown machine ids in the scope map (not in the registry) render with the raw id and a hint", () => {
    seed({ scope: { "M-GHOST": "*" }, axes: ["machine"], machines: [LOCAL] });
    render(<ScopeCard kind="agent" name="cur" />);
    const row = within(screen.getByTestId("scope-row-M-GHOST"));
    expect(row.getByText("M-GHOST")).toBeInTheDocument();
    expect(row.getByText(/unknown/i)).toBeInTheDocument();
  });

  test("shows a not-active-here hint when custom scope excludes the local machine", () => {
    seed({ scope: { "M-OTHER": "*" }, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    expect(screen.getByText(/not active on this machine/i)).toBeInTheDocument();
  });

  test("no not-active-here hint when the local machine is included", () => {
    seed({ scope: { "M-LOCAL": "*" }, axes: ["machine"] });
    render(<ScopeCard kind="agent" name="cur" />);
    expect(screen.queryByText(/not active on this machine/i)).not.toBeInTheDocument();
  });

  test("toggling a row on preserves unknown machines in scope", () => {
    seed({
      scope: { "M-LOCAL": "*", "M-GHOST": "*" },
      axes: ["machine"],
      machines: [LOCAL],
    });
    render(<ScopeCard kind="agent" name="cur" />);
    const row = within(screen.getByTestId("scope-row-M-LOCAL"));
    // First turn M-LOCAL off, then back on to verify M-GHOST is preserved
    fireEvent.click(row.getByRole("switch"));
    expect(mutate).toHaveBeenCalledWith({ "M-GHOST": "*" });
  });
});
