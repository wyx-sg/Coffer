import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AgentModelBar } from "./AgentModelBar";

vi.mock("@/lib/hooks/useConversations", () => ({
  useAgentConfig: vi.fn(),
  useSetAgentModel: vi.fn(),
  useSetAgentEffort: vi.fn(),
}));
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));
// The picker reads the agent's catalogue from the daemon; stub that boundary too
// so the bar renders without a QueryClientProvider.
vi.mock("@/lib/hooks/useAgentModels", () => ({ useAgentModels: vi.fn() }));

import { useAgentConfig, useSetAgentEffort, useSetAgentModel } from "@/lib/hooks/useConversations";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

const useAgentConfigMock = useAgentConfig as unknown as ReturnType<typeof vi.fn>;
const useSetAgentModelMock = useSetAgentModel as unknown as ReturnType<typeof vi.fn>;
const useSetAgentEffortMock = useSetAgentEffort as unknown as ReturnType<typeof vi.fn>;
const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;
const useAgentModelsMock = useAgentModels as unknown as ReturnType<typeof vi.fn>;

const mutate = vi.fn();
const mutateEffort = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  useAgentConfigMock.mockReturnValue({
    data: { cwd: null, model: "claude-opus-4-8", effort: null },
  });
  useSetAgentModelMock.mockReturnValue({ mutate });
  useSetAgentEffortMock.mockReturnValue({ mutate: mutateEffort });
  useProvidersMock.mockReturnValue({ data: [] });
  useListMock.mockReturnValue({ mutate: vi.fn() });
  // The daemon serves the agent's catalogue; "haiku" stands in for a curated alias.
  useAgentModelsMock.mockReturnValue({
    data: [{ id: "haiku", label: "", description: "", efforts: [], default_effort: null }],
  });
});

describe("AgentModelBar", () => {
  test("shows the agent label and the conversation's current model", () => {
    render(<AgentModelBar conversationId="c1" agentKey="claude_code" agentLabel="Claude Code" />);
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    // The picker is a fixed dropdown; its trigger reflects the current value.
    expect(screen.getByRole("combobox", { name: /agent model/i })).toHaveTextContent(
      "claude-opus-4-8",
    );
  });

  test("committing a new model calls setAgentModel with the conversation id", () => {
    useAgentConfigMock.mockReturnValue({ data: { cwd: null, model: null, effort: null } });
    render(<AgentModelBar conversationId="c1" agentKey="claude_code" agentLabel="Claude Code" />);
    // No override → the agent's catalogue is offered; pick one from the dropdown.
    fireEvent.keyDown(screen.getByRole("combobox", { name: /agent model/i }), { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "haiku" }));
    expect(mutate).toHaveBeenCalledWith({ id: "c1", model: "haiku" });
  });

  test("disables the picker for a read-only (archived) conversation", () => {
    render(
      <AgentModelBar
        conversationId="c1"
        agentKey="claude_code"
        agentLabel="Claude Code"
        disabled
      />,
    );
    expect(screen.getByRole("combobox", { name: /agent model/i })).toBeDisabled();
  });

  test("shows no effort control for an agent whose models take none", () => {
    // Claude Code's bar must look exactly as it did before the effort existed.
    render(<AgentModelBar conversationId="c1" agentKey="claude_code" agentLabel="Claude Code" />);
    expect(screen.queryByRole("combobox", { name: /reasoning effort/i })).toBeNull();
  });

  describe("with a model that reports reasoning levels", () => {
    beforeEach(() => {
      useAgentConfigMock.mockReturnValue({
        data: { cwd: null, model: "gpt-5-codex", effort: "low" },
      });
      useAgentModelsMock.mockReturnValue({
        data: [
          {
            id: "gpt-5-codex",
            label: "",
            description: "",
            efforts: ["low", "medium", "high", "xhigh"],
            default_effort: "xhigh",
          },
        ],
      });
    });

    test("shows the effort control on the conversation's current level", () => {
      render(<AgentModelBar conversationId="c1" agentKey="codex" agentLabel="Codex" />);
      expect(screen.getByRole("combobox", { name: /reasoning effort/i })).toHaveTextContent("low");
    });

    test("picking a level patches the effort ALONE, leaving the model untouched", () => {
      render(<AgentModelBar conversationId="c1" agentKey="codex" agentLabel="Codex" />);
      fireEvent.keyDown(screen.getByRole("combobox", { name: /reasoning effort/i }), {
        key: "ArrowDown",
      });
      fireEvent.click(screen.getByRole("option", { name: "high" }));
      expect(mutateEffort).toHaveBeenCalledWith({ id: "c1", effort: "high" });
      expect(mutate).not.toHaveBeenCalled();
    });

    test("the inherit sentinel clears the effort", () => {
      render(<AgentModelBar conversationId="c1" agentKey="codex" agentLabel="Codex" />);
      fireEvent.keyDown(screen.getByRole("combobox", { name: /reasoning effort/i }), {
        key: "ArrowDown",
      });
      fireEvent.click(screen.getByRole("option", { name: /^Agent default/ }));
      expect(mutateEffort).toHaveBeenCalledWith({ id: "c1", effort: null });
      expect(mutate).not.toHaveBeenCalled();
    });

    test("disables the effort control for a read-only (archived) conversation", () => {
      render(<AgentModelBar conversationId="c1" agentKey="codex" agentLabel="Codex" disabled />);
      expect(screen.getByRole("combobox", { name: /reasoning effort/i })).toBeDisabled();
    });
  });
});
