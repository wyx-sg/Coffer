// frontend/src/components/agents/AgentMemoryDelivery.test.tsx
//
// One agent's delivery state, on that agent's own page (spec memory
// FR-054/FR-055, ADR aggregate-agent-memory-never-write-it): "installed" is
// not the signal, "last fired" is — an installed hook that never actually ran
// must render as a warning, not a success, because that is exactly the failure
// mode the removed injection layer had for two months with nothing saying so.
//
// The agent is fixed by the page, so this surface asks for one agent and shows
// no picker; it must not re-introduce the list of agents it replaced.
import { describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { AgentMemoryDelivery } from "./AgentMemoryDelivery";
import type { DeliveryStatusOut } from "@/lib/api/memoryTypes";

vi.mock("@/lib/hooks/useMemory", () => ({
  useMemoryDelivery: vi.fn(),
  useInstallDelivery: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveDelivery: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useMemoryDelivery } = await import("@/lib/hooks/useMemory");
const deliveryMock = vi.mocked(useMemoryDelivery);

function mockStatus(rows: DeliveryStatusOut[]) {
  deliveryMock.mockReturnValue({
    data: rows,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useMemoryDelivery>);
}

const FIRED: DeliveryStatusOut = {
  agent: "claude_code",
  installed: true,
  command: "coffer memory context --agent claude_code",
  last_fired_at: "2026-09-12T10:00:00Z",
  event: "SessionStart",
};

describe("AgentMemoryDelivery", () => {
  test("asks only about the agent whose page this is, and shows no picker", () => {
    // The list-of-agents surface this replaced made the reader choose an agent
    // they had already navigated to; the agent is the page, so it is a prop.
    mockStatus([FIRED]);
    render(<AgentMemoryDelivery agentName="claude_code" />);
    expect(deliveryMock).toHaveBeenCalledWith("claude_code");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/codex/i)).toBeNull();
  });

  test("an installed-but-never-fired delivery renders as a warning", () => {
    mockStatus([{ ...FIRED, agent: "codex", event: "UserPromptSubmit", last_fired_at: "" }]);
    render(<AgentMemoryDelivery agentName="codex" />);

    // Scoped to the status block: the card's own subtitle says "last fired is"
    // too, so an unscoped query would match the explainer, not the state.
    const state = within(screen.getByTestId("memory-delivery-codex"));
    expect(screen.getByTestId("memory-delivery-warning-codex")).toBeInTheDocument();
    expect(state.getByText(/never fired/i)).toBeInTheDocument();
    // Not the plain success styling a fired install gets.
    expect(state.queryByText(/last fired/i)).toBeNull();
  });

  test("an installed delivery that has fired shows when, and no warning", () => {
    mockStatus([FIRED]);
    render(<AgentMemoryDelivery agentName="claude_code" />);

    const state = within(screen.getByTestId("memory-delivery-claude_code"));
    expect(screen.queryByTestId("memory-delivery-warning-claude_code")).toBeNull();
    expect(state.getByText(/last fired/i)).toBeInTheDocument();
  });

  test("a not-installed agent offers Install, not Remove", () => {
    mockStatus([{ ...FIRED, installed: false, last_fired_at: "" }]);
    render(<AgentMemoryDelivery agentName="claude_code" />);

    expect(screen.getByRole("button", { name: /install/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).toBeNull();
  });

  test("an agent type with no hook event says so rather than offering Install", () => {
    // `status(agent)` answers for the one agent asked about; a type delivery
    // cannot attach to yields nothing, and an Install button that could only
    // fail would be worse than a sentence.
    mockStatus([]);
    render(<AgentMemoryDelivery agentName="claude_code" />);

    expect(screen.getByText(/no hook event/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /install/i })).toBeNull();
  });
});
