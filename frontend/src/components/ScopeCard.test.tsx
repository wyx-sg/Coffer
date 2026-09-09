// frontend/src/components/ScopeCard.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ScopeCard } from "./ScopeCard";
import type { Scope } from "@/lib/hooks/useScope";

vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(),
  useUpdateResourceScope: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));

const scopeHooks = await import("@/lib/hooks/useScope");
const agentHooks = await import("@/lib/hooks/useAgents");

const mutate = vi.fn();

function seed(opts: { scope: Scope | null; supported?: boolean; agents?: { name: string }[] }) {
  const { scope, supported = true, agents = [{ name: "claude" }, { name: "codex" }] } = opts;
  vi.mocked(scopeHooks.useResourceScope).mockReturnValue({
    data: { scope, supported },
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useResourceScope>);
  vi.mocked(scopeHooks.useUpdateResourceScope).mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof scopeHooks.useUpdateResourceScope>);
  vi.mocked(agentHooks.useAgents).mockReturnValue({
    data: agents,
  } as unknown as ReturnType<typeof agentHooks.useAgents>);
}

afterEach(() => vi.clearAllMocks());

describe("ScopeCard", () => {
  test("renders nothing for a kind that declares no scope", () => {
    seed({ scope: null, supported: false });
    const { container } = render(<ScopeCard kind="channel" name="tg" />);
    expect(container).toBeEmptyDOMElement();
  });

  test("every-agent mode shows no agent checkboxes", () => {
    seed({ scope: null });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    expect(screen.getByRole("button", { name: /every agent/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /selected agents/i })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("switching every-agent -> selected PUTs an empty list", () => {
    seed({ scope: null });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("button", { name: /selected agents/i }));
    expect(mutate).toHaveBeenCalledWith([]);
  });

  test("switching selected -> every-agent PUTs null", () => {
    seed({ scope: ["claude"] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("button", { name: /every agent/i }));
    expect(mutate).toHaveBeenCalledWith(null);
  });

  test("dormant warning renders for an empty selection", () => {
    seed({ scope: [] });
    render(<ScopeCard kind="skill" name="writing" />);
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
  });

  test("no dormant warning once at least one agent is selected", () => {
    seed({ scope: ["claude"] });
    render(<ScopeCard kind="skill" name="writing" />);
    expect(screen.queryByText(/dormant/i)).not.toBeInTheDocument();
  });

  test("checking an agent adds it to the list", () => {
    seed({ scope: ["claude"] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "codex" }));
    expect(mutate).toHaveBeenCalledWith(["claude", "codex"]);
  });

  test("unchecking the last agent PUTs an empty list", () => {
    seed({ scope: ["claude"] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "claude" }));
    expect(mutate).toHaveBeenCalledWith([]);
  });

  test("an agent registered here but not selected renders unchecked", () => {
    seed({ scope: ["claude"] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    expect(screen.getByRole("checkbox", { name: "claude" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "codex" })).not.toBeChecked();
  });

  test("a scoped-in agent that is not registered here renders with an unknown hint", () => {
    seed({ scope: ["ghost"], agents: [{ name: "claude" }] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    const row = within(screen.getByTestId("scope-agent-ghost"));
    expect(row.getByText("ghost")).toBeInTheDocument();
    expect(row.getByText(/not registered/i)).toBeInTheDocument();
  });

  test("selecting an agent preserves unregistered names already in scope", () => {
    seed({ scope: ["ghost"], agents: [{ name: "claude" }] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "claude" }));
    expect(mutate).toHaveBeenCalledWith(["ghost", "claude"]);
  });

  test("shows the empty hint when no agent is registered and none is scoped", () => {
    seed({ scope: [], agents: [] });
    render(<ScopeCard kind="mcp_server" name="fs" />);
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });
});
