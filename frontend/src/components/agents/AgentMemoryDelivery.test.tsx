// frontend/src/components/agents/AgentMemoryDelivery.test.tsx
//
// One agent's delivery state, on that agent's own page (spec memory
// FR-025/FR-026, ADR aggregate-agent-memory-never-write-it). The card answers
// exactly one question — installed or not. Whether the hook has fired is a
// stream of events and is read on the Activity page, one audit entry per fire,
// so this surface must not speculate about it.
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

const INSTALLED: DeliveryStatusOut = {
  agent: "claude_code",
  installed: true,
  command: "coffer memory context --agent claude_code",
  event: "SessionStart",
};

describe("AgentMemoryDelivery", () => {
  test("asks only about the agent whose page this is, and shows no picker", () => {
    // The list-of-agents surface this replaced made the reader choose an agent
    // they had already navigated to; the agent is the page, so it is a prop.
    mockStatus([INSTALLED]);
    render(<AgentMemoryDelivery agentName="claude_code" />);
    expect(deliveryMock).toHaveBeenCalledWith("claude_code");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/codex/i)).toBeNull();
  });

  test("an installed delivery says installed and nothing about firing", () => {
    // Firing is a stream of events, reported in the audit log. A card that
    // guessed at it — "never fired" on a hook installed a minute ago — would
    // be alarming and wrong, which is why this surface no longer tries.
    mockStatus([{ ...INSTALLED, agent: "codex", event: "UserPromptSubmit" }]);
    render(<AgentMemoryDelivery agentName="codex" />);

    const state = within(screen.getByTestId("memory-delivery-codex"));
    expect(state.getByText(/installed/i)).toBeInTheDocument();
    expect(state.queryByText(/never fired/i)).toBeNull();
    expect(state.queryByText(/last fired/i)).toBeNull();
    expect(screen.queryByTestId("memory-delivery-warning-codex")).toBeNull();
  });

  test("a not-installed agent offers Install, not Remove", () => {
    mockStatus([{ ...INSTALLED, installed: false }]);
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
