// frontend/src/components/agents/AgentMemoryDelivery.test.tsx
//
// One agent's delivery state, on that agent's own page (spec memory "Show
// delivery state on the agent's own page", ADR
// aggregate-agent-memory-never-write-it). The card answers
// exactly one question — installed or not. Whether the hook has fired is a
// stream of events and is read on the Activity page, one audit entry per fire,
// so this surface must not speculate about it.
//
// The agent is fixed by the page, so this surface asks for one agent and shows
// no picker; it must not re-introduce the list of agents it replaced.
//
// A delivery row carries both halves of the agent's identity and the card uses
// each for one thing: the query and the install/remove requests are addressed
// to `agent_uid`, while the card's testid and the removal confirmation read
// `agent_name`. The fixtures keep the two apart on purpose.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { AgentMemoryDelivery } from "./AgentMemoryDelivery";
import type { DeliveryStatusOut } from "@/lib/api/memoryTypes";

vi.mock("@/lib/hooks/useMemory", () => ({
  useMemoryDelivery: vi.fn(),
  useInstallDelivery: vi.fn(),
  useRemoveDelivery: vi.fn(),
}));

const { useMemoryDelivery, useInstallDelivery, useRemoveDelivery } =
  await import("@/lib/hooks/useMemory");
const deliveryMock = vi.mocked(useMemoryDelivery);
const installMock = vi.mocked(useInstallDelivery);
const removeMock = vi.mocked(useRemoveDelivery);

/** Both mutations, stubbed; the returned spy is the install one, which the
 *  install test asserts is addressed to the uid. */
function stubMutations() {
  const install = vi.fn();
  installMock.mockReturnValue({
    mutate: install,
    isPending: false,
  } as unknown as ReturnType<typeof useInstallDelivery>);
  removeMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveDelivery>);
  return install;
}

function mockStatus(rows: DeliveryStatusOut[]) {
  deliveryMock.mockReturnValue({
    data: rows,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useMemoryDelivery>);
}

const INSTALLED: DeliveryStatusOut = {
  agent_uid: "u-claude-code",
  agent_name: "claude_code",
  installed: true,
  // The hook the daemon writes names the agent by uid, so a rename cannot
  // leave an installed hook pointing at nothing.
  command: "coffer memory context --agent-uid u-claude-code",
  event: "SessionStart",
};

describe("AgentMemoryDelivery", () => {
  test("asks only about the agent whose page this is, and shows no picker", () => {
    // The list-of-agents surface this replaced made the reader choose an agent
    // they had already navigated to; the agent is the page, so it is a prop.
    stubMutations();
    mockStatus([INSTALLED]);
    render(<AgentMemoryDelivery agentUid="u-claude-code" />);
    expect(deliveryMock).toHaveBeenCalledWith("u-claude-code");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/codex/i)).toBeNull();
  });

  test("an installed delivery says installed and nothing about firing", () => {
    // Firing is a stream of events, reported in the audit log. A card that
    // guessed at it — "never fired" on a hook installed a minute ago — would
    // be alarming and wrong, which is why this surface no longer tries.
    stubMutations();
    mockStatus([
      {
        ...INSTALLED,
        agent_uid: "u-codex",
        agent_name: "codex",
        event: "UserPromptSubmit",
      },
    ]);
    render(<AgentMemoryDelivery agentUid="u-codex" />);

    // The card is found by the agent's NAME: a testid is a handle a person
    // writes and reads, and the uid says nothing to either.
    const state = within(screen.getByTestId("memory-delivery-codex"));
    expect(state.getByText(/installed/i)).toBeInTheDocument();
    expect(state.queryByText(/never fired/i)).toBeNull();
    expect(state.queryByText(/last fired/i)).toBeNull();
    expect(screen.queryByTestId("memory-delivery-warning-codex")).toBeNull();
  });

  test("a not-installed agent offers Install, and installs by uid", () => {
    const install = stubMutations();
    mockStatus([{ ...INSTALLED, installed: false }]);
    render(<AgentMemoryDelivery agentUid="u-claude-code" />);

    const button = screen.getByRole("button", { name: /install/i });
    expect(button).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).toBeNull();

    // The row named the agent; the write is addressed to its uid.
    fireEvent.click(button);
    expect(install).toHaveBeenCalledWith("u-claude-code");
  });

  test("an agent type with no hook event says so rather than offering Install", () => {
    // `status(agent)` answers for the one agent asked about; a type delivery
    // cannot attach to yields nothing, and an Install button that could only
    // fail would be worse than a sentence.
    stubMutations();
    mockStatus([]);
    render(<AgentMemoryDelivery agentUid="u-claude-code" />);

    expect(screen.getByText(/no hook event/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /install/i })).toBeNull();
  });

  acceptance("memory", "show installed or not on the agent page", () => {
    // Two agents' pages: one with delivery installed, one without. Each card
    // answers installed-or-not, offers the one action that matches, and
    // carries no last-fired time — a fire is an event on the Activity page.
    stubMutations();
    const notInstalled: DeliveryStatusOut = {
      ...INSTALLED,
      agent_uid: "u-codex",
      agent_name: "codex",
      installed: false,
      event: "SessionStart",
    };
    deliveryMock.mockImplementation(
      (uid?: string) =>
        ({
          data: uid === "u-codex" ? [notInstalled] : [INSTALLED],
          isPending: false,
          error: null,
        }) as unknown as ReturnType<typeof useMemoryDelivery>,
    );

    const { unmount } = render(<AgentMemoryDelivery agentUid="u-claude-code" />);
    const installed = within(screen.getByTestId("memory-delivery-claude_code"));
    expect(installed.getByText(/^installed$/i)).toBeInTheDocument();
    expect(installed.getByRole("button", { name: /remove/i })).toBeInTheDocument();
    expect(installed.queryByRole("button", { name: /^install$/i })).toBeNull();
    expect(screen.queryByText(/last fired|never fired|fired at|ago\b/i)).toBeNull();
    unmount();

    render(<AgentMemoryDelivery agentUid="u-codex" />);
    const absent = within(screen.getByTestId("memory-delivery-codex"));
    expect(absent.getByText(/^not installed$/i)).toBeInTheDocument();
    expect(absent.getByRole("button", { name: /^install$/i })).toBeInTheDocument();
    expect(absent.queryByRole("button", { name: /remove/i })).toBeNull();
    expect(screen.queryByText(/last fired|never fired|fired at|ago\b/i)).toBeNull();
  });
});
