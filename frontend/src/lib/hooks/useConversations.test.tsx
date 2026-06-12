// frontend/src/lib/hooks/useConversations.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import {
  useConversations,
  useConversation,
  useCreateConversation,
  useRenameConversation,
  useDeleteConversation,
  useSetConversationModel,
} from "./useConversations";
import type { Conversation } from "@/lib/api/chat";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    updateConversation: vi.fn(),
    deleteConversation: vi.fn(),
    listMessages: vi.fn(),
  },
}));

// onError → toast is the default for every mutation (agents/frontend.md §5):
// a failed mutation must announce itself, not fail silently. Spy the toast.
const errorToast = vi.fn();
vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return {
    ...actual,
    useToast: () => ({
      toast: { error: errorToast, success: vi.fn(), info: vi.fn() },
      dismiss: vi.fn(),
    }),
  };
});

const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

function makeConversation(overrides?: Partial<Conversation>): Conversation {
  return {
    id: "conv-1",
    agent_key: "builtin",
    title: "Test Conversation",
    model_id: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    ...overrides,
  };
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useConversations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("returns list of conversations on success", async () => {
    const conv = makeConversation();
    chatApiMock.listConversations.mockResolvedValue({ conversations: [conv] });

    const { result } = renderHook(() => useConversations(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].id).toBe("conv-1");
  });

  test("returns empty array when no conversations", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });

    const { result } = renderHook(() => useConversations(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });

  test("throws on API error", async () => {
    chatApiMock.listConversations.mockRejectedValue(new Error("network failure"));

    const { result } = renderHook(() => useConversations(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("network failure");
  });
});

describe("useConversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches and returns a single conversation by id", async () => {
    const conv = makeConversation({ id: "conv-42", title: "Single Conv" });
    chatApiMock.getConversation.mockResolvedValue(conv);

    const { result } = renderHook(() => useConversation("conv-42"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe("conv-42");
    expect(result.current.data?.title).toBe("Single Conv");
    expect(chatApiMock.getConversation).toHaveBeenCalledWith("conv-42");
  });

  test("is disabled when id is empty string", async () => {
    const { result } = renderHook(() => useConversation(""), {
      wrapper: makeWrapper(),
    });

    // With enabled:false the query stays in 'pending' state and never calls the API.
    expect(result.current.fetchStatus).toBe("idle");
    expect(chatApiMock.getConversation).not.toHaveBeenCalled();
  });

  test("surfaces API error", async () => {
    chatApiMock.getConversation.mockRejectedValue(new Error("not found"));

    const { result } = renderHook(() => useConversation("bad-id"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("not found");
  });
});

describe("useCreateConversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("creates a conversation and the mutation succeeds", async () => {
    const conv = makeConversation({ id: "new-conv" });
    chatApiMock.createConversation.mockResolvedValue(conv);
    chatApiMock.listConversations.mockResolvedValue({ conversations: [conv] });

    const { result } = renderHook(() => useCreateConversation(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync(undefined);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe("new-conv");
  });

  test("passes agent_key and agent_config when provided", async () => {
    const conv = makeConversation({ model_id: "model-1" });
    chatApiMock.createConversation.mockResolvedValue(conv);
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });

    const { result } = renderHook(() => useCreateConversation(), {
      wrapper: makeWrapper(),
    });

    const body = { agent_key: "builtin", agent_config: { model_id: "model-1" } };
    await act(async () => {
      await result.current.mutateAsync(body);
    });

    expect(chatApiMock.createConversation).toHaveBeenCalledWith(body);
  });
});

describe("useRenameConversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("calls updateConversation with the new title and mutation succeeds", async () => {
    const updated = makeConversation({ title: "New Name" });
    chatApiMock.updateConversation.mockResolvedValue(updated);
    chatApiMock.listConversations.mockResolvedValue({ conversations: [updated] });

    const { result } = renderHook(() => useRenameConversation(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ id: "conv-1", title: "New Name" });
    });

    expect(chatApiMock.updateConversation).toHaveBeenCalledWith("conv-1", { title: "New Name" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe("useSetConversationModel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("calls updateConversation with model_id", async () => {
    const updated = makeConversation({ model_id: "model-x" });
    chatApiMock.updateConversation.mockResolvedValue(updated);
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });

    const { result } = renderHook(() => useSetConversationModel(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ id: "conv-1", model_id: "model-x" });
    });

    expect(chatApiMock.updateConversation).toHaveBeenCalledWith("conv-1", {
      model_id: "model-x",
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe("useDeleteConversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("deletes a conversation and mutation succeeds", async () => {
    chatApiMock.deleteConversation.mockResolvedValue(undefined);
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });

    const { result } = renderHook(() => useDeleteConversation(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync("conv-1");
    });

    expect(chatApiMock.deleteConversation).toHaveBeenCalledWith("conv-1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  test("toasts an error when the delete fails (not silent)", async () => {
    chatApiMock.deleteConversation.mockRejectedValue(new Error("server down"));

    const { result } = renderHook(() => useDeleteConversation(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync("conv-1").catch(() => {});
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(errorToast).toHaveBeenCalledTimes(1);
    expect(errorToast).toHaveBeenCalledWith(expect.stringContaining("server down"));
  });
});

describe("conversation mutation error toasts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("rename failure surfaces a toast", async () => {
    chatApiMock.updateConversation.mockRejectedValue(new Error("rename boom"));

    const { result } = renderHook(() => useRenameConversation(), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ id: "conv-1", title: "x" }).catch(() => {});
    });

    await waitFor(() => expect(errorToast).toHaveBeenCalledWith(expect.stringContaining("rename boom")));
  });
});
