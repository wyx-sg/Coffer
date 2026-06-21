import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AgentModelBar } from "./AgentModelBar";

vi.mock("@/lib/hooks/useConversations", () => ({
  useAgentConfig: vi.fn(),
  useSetAgentModel: vi.fn(),
}));
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: vi.fn() }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({ useListProviderModels: vi.fn() }));

import { useAgentConfig, useSetAgentModel } from "@/lib/hooks/useConversations";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

const useAgentConfigMock = useAgentConfig as unknown as ReturnType<typeof vi.fn>;
const useSetAgentModelMock = useSetAgentModel as unknown as ReturnType<typeof vi.fn>;
const useProvidersMock = useProviders as unknown as ReturnType<typeof vi.fn>;
const useListMock = useListProviderModels as unknown as ReturnType<typeof vi.fn>;

const mutate = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  useAgentConfigMock.mockReturnValue({ data: { cwd: null, model: "claude-opus-4-8" } });
  useSetAgentModelMock.mockReturnValue({ mutate });
  useProvidersMock.mockReturnValue({ data: [] });
  useListMock.mockReturnValue({ mutate: vi.fn() });
});

describe("AgentModelBar", () => {
  test("shows the agent label and the conversation's current model", () => {
    render(<AgentModelBar conversationId="c1" agentKey="claude_code" agentLabel="Claude Code" />);
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByLabelText(/agent model/i)).toHaveValue("claude-opus-4-8");
  });

  test("committing a new model calls setAgentModel with the conversation id", () => {
    render(<AgentModelBar conversationId="c1" agentKey="claude_code" agentLabel="Claude Code" />);
    const picker = screen.getByLabelText(/agent model/i);
    fireEvent.change(picker, { target: { value: "claude-haiku-4-5" } });
    fireEvent.blur(picker);
    expect(mutate).toHaveBeenCalledWith({ id: "c1", model: "claude-haiku-4-5" });
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
    expect(screen.getByLabelText(/agent model/i)).toBeDisabled();
  });
});
