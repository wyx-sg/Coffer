// frontend/src/lib/hooks/useChatController.test.tsx
//
// The draft → create → first-message flow, from the controller's side. What is
// pinned here is what the DRAFT carries into the conversation it creates: the
// agent, the folder and the model. The first turn fires the moment the
// conversation exists, so a model not carried in the create call is a model the
// first turn never ran on.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("./useConversations", () => ({
  useConversation: () => ({ data: null, isPending: false }),
  useCreateConversation: () => createConv,
  useRenameConversation: () => ({ mutate: vi.fn() }),
  useDeleteConversation: () => ({ mutate: vi.fn(), isPending: false }),
  useArchiveConversation: () => ({ mutate: vi.fn(), isPending: false }),
  useUnarchiveConversation: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("./useConversationList", () => ({
  useConversationList: () => ({
    items: [],
    isLoading: false,
    isLoadingMore: false,
    hasMore: false,
    loadMore: vi.fn(),
  }),
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
  useLocation: () => location,
  useParams: () => route,
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

import { useChatController } from "./useChatController";

const navigate = vi.fn();
let route: { id?: string } = {};
let location: { pathname: string; search: string; state: unknown } = {
  pathname: "/conversations",
  search: "",
  state: null,
};
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
  route = {};
  location = { pathname: "/conversations", search: "", state: null };
});

describe("useChatController draft", () => {
  test("carries the chosen model into the conversation it creates", () => {
    const { result } = renderHook(() => useChatController());

    act(() => result.current.setDraftModel("opus"));
    act(() => {
      void result.current.sendDraft("first message");
    });

    expect(createdWith()).toEqual({ model: "opus" });
  });

  test("an unset model is omitted, so the agent runs on its own", () => {
    // Sending nothing is not the same as sending an empty string: the backend
    // reads a present-but-empty field as "clear it", and there is nothing to
    // clear on a conversation that does not exist yet.
    const { result } = renderHook(() => useChatController());

    act(() => {
      void result.current.sendDraft("first message");
    });

    expect(createdWith()).toEqual({});
  });

  test("switching agent drops the model", () => {
    const { result } = renderHook(() => useChatController());

    act(() => result.current.setDraftModel("gpt-5-codex"));
    act(() => result.current.setDraftAgent("claude_code"));

    // The folder stays: it is where the work is, whichever agent does it.
    expect(result.current.effectiveDraft).toEqual({
      agentKey: "claude_code",
      cwd: null,
      model: null,
    });
  });
});

describe("useChatController hand-off", () => {
  test("seeds the draft once from the location state, then clears it", () => {
    route = { id: "new" };
    location = {
      pathname: "/conversations/new",
      search: "",
      state: { handoff: { agentKey: "codex", cwd: "/w", prompt: "Install jq." } },
    };
    const { result } = renderHook(() => useChatController());

    expect(result.current.effectiveDraft).toEqual({
      agentKey: "codex",
      cwd: "/w",
      model: null,
    });
    expect(result.current.draftPrefill).toEqual({ text: "Install jq.", attachments: [] });
    // The history entry loses the state, so a reload or Back does not type it again.
    expect(navigate).toHaveBeenCalledWith("/conversations/new", { replace: true, state: null });
    // Pre-filling creates nothing.
    expect(createConv.mutate).not.toHaveBeenCalled();

    act(() => result.current.clearDraftPrefill());
    expect(result.current.draftPrefill).toBeNull();
  });

  test("a hand-off marked autoSend creates the conversation at once, once", () => {
    route = { id: "new" };
    location = {
      pathname: "/conversations/new",
      search: "",
      state: { handoff: { agentKey: "codex", cwd: "/w", prompt: "Tidy.", autoSend: true } },
    };
    const { rerender } = renderHook(() => useChatController());
    rerender();
    rerender();

    expect(createConv.mutate).toHaveBeenCalledTimes(1);
    expect(createConv.mutate.mock.calls[0]?.[0]).toEqual({
      agent_key: "codex",
      agent_config: { cwd: "/w" },
    });
  });

  test("a plain hand-off sends nothing", () => {
    route = { id: "new" };
    location = {
      pathname: "/conversations/new",
      search: "",
      state: { handoff: { agentKey: "codex", cwd: null, prompt: "Install jq." } },
    };
    renderHook(() => useChatController());
    expect(createConv.mutate).not.toHaveBeenCalled();
  });

  test("an agent page's New conversation opens an empty draft on that agent", () => {
    route = { id: "new" };
    location = { pathname: "/conversations/new", search: "", state: { draftAgent: "codex" } };
    const { result } = renderHook(() => useChatController());

    expect(result.current.effectiveDraft.agentKey).toBe("codex");
    expect(result.current.draftPrefill).toBeNull();
    expect(result.current.draftFromHandoff).toBe(false);
    expect(navigate).toHaveBeenCalledWith("/conversations/new", { replace: true, state: null });
    expect(createConv.mutate).not.toHaveBeenCalled();
  });

  test("a hand-off in the state of any other page is ignored", () => {
    location = {
      pathname: "/conversations",
      search: "",
      state: { handoff: { agentKey: "codex", cwd: null, prompt: "Install jq." } },
    };
    const { result } = renderHook(() => useChatController());
    expect(result.current.draftPrefill).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });
});
