// frontend/src/lib/hooks/useChatController.test.tsx
//
// The draft → create → first-message flow, from the controller's side. What is
// pinned here is what the DRAFT carries into the conversation it creates: the
// agent, the model, and — the half that used to have nowhere to be chosen — the
// reasoning effort. The first turn fires the moment the conversation exists, so
// a level not carried in the create call is a level the first turn never ran at.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("./useConversations", () => ({
  useConversations: () => ({ data: [], isPending: false }),
  useArchivedConversations: () => ({ data: [], isPending: false }),
  useConversation: () => ({ data: null, isPending: false }),
  useCreateConversation: () => createConv,
  useRenameConversation: () => ({ mutate: vi.fn() }),
  useDeleteConversation: () => ({ mutate: vi.fn(), isPending: false }),
  useArchiveConversation: () => ({ mutate: vi.fn(), isPending: false }),
  useUnarchiveConversation: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("./useAgentProviders", () => ({
  useAgentProviders: () => ({
    data: [
      { agent_key: "claude_code", display_name: "Claude Code", available: true },
      { agent_key: "codex", display_name: "Codex", available: true },
    ],
  }),
}));
vi.mock("./useChatTurn", () => ({
  useChatTurn: () => ({ send: vi.fn(), setPending: vi.fn() }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useParams: () => ({}),
}));

import { useChatController } from "./useChatController";

const navigate = vi.fn();
const createConv = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null,
  reset: vi.fn(),
};

/** The agent_config the draft asked the API to create the conversation with. */
function createdWith(): Record<string, unknown> {
  const [body] = createConv.mutate.mock.calls.at(-1) ?? [];
  return (body as { agent_config: Record<string, unknown> }).agent_config;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useChatController draft", () => {
  test("carries the chosen effort into the conversation it creates", () => {
    const { result } = renderHook(() => useChatController());

    act(() => result.current.setDraftModel("opus"));
    act(() => result.current.setDraftEffort("xhigh"));
    act(() => result.current.sendDraft("first message"));

    expect(createdWith()).toEqual({ model: "opus", effort: "xhigh" });
  });

  test("an unset effort is omitted, so the agent runs at its own level", () => {
    // Sending nothing is not the same as sending an empty string: the backend
    // reads a present-but-empty field as "clear it", and there is nothing to
    // clear on a conversation that does not exist yet.
    const { result } = renderHook(() => useChatController());

    act(() => result.current.sendDraft("first message"));

    expect(createdWith()).toEqual({});
  });

  test("switching agent drops the effort with the model", () => {
    // A level is the agent's own vocabulary — carrying `xhigh` from Codex to an
    // agent that has never heard of it would pin the first turn to a name its
    // CLI would reject.
    const { result } = renderHook(() => useChatController());

    act(() => result.current.setDraftModel("gpt-5-codex"));
    act(() => result.current.setDraftEffort("xhigh"));
    act(() => result.current.setDraftAgent("claude_code"));

    expect(result.current.effectiveDraft).toEqual({
      agentKey: "claude_code",
      model: null,
      effort: null,
    });
  });

  test("switching model keeps the effort", () => {
    // The picker keeps a level it no longer offers selectable rather than
    // dropping it silently, so the trigger never misreports the first turn.
    const { result } = renderHook(() => useChatController());

    act(() => result.current.setDraftEffort("high"));
    act(() => result.current.setDraftModel("sonnet"));

    expect(result.current.effectiveDraft.effort).toBe("high");
    expect(result.current.effectiveDraft.model).toBe("sonnet");
  });
});
