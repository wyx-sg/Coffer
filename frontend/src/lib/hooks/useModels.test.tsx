// frontend/src/lib/hooks/useModels.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useModels, useCreateModel, useUpdateModel, useDeleteModel } from "./useModels";
import type { Model } from "@/lib/api/models";

vi.mock("@/lib/api/models", () => ({
  modelsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}));

const { modelsApi } = await import("@/lib/api/models");
const modelsApiMock = modelsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

function makeModel(overrides?: Partial<Model>): Model {
  return {
    id: "model-1",
    display_name: "Claude Sonnet",
    provider: "anthropic",
    model: "claude-sonnet-4-6",
    credential_ref: "my-cred",
    base_url: null,
    is_default: true,
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

describe("useModels", () => {
  beforeEach(() => vi.clearAllMocks());

  test("returns list of models on success", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });

    const { result } = renderHook(() => useModels(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].id).toBe("model-1");
  });

  test("throws on API error", async () => {
    modelsApiMock.list.mockRejectedValue(new Error("api down"));

    const { result } = renderHook(() => useModels(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("api down");
  });
});

describe("useCreateModel", () => {
  beforeEach(() => vi.clearAllMocks());

  test("creates a model and mutation succeeds", async () => {
    const m = makeModel({ id: "model-2" });
    modelsApiMock.create.mockResolvedValue(m);
    modelsApiMock.list.mockResolvedValue({ models: [m] });

    const { result } = renderHook(() => useCreateModel(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.mutateAsync({
        display_name: "Claude Sonnet",
        provider: "anthropic",
        model: "claude-sonnet-4-6",
        credential_ref: "my-cred",
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(modelsApiMock.create).toHaveBeenCalledOnce();
  });
});

describe("useUpdateModel", () => {
  beforeEach(() => vi.clearAllMocks());

  test("updates a model and mutation succeeds", async () => {
    const updated = makeModel({ display_name: "Updated Name" });
    modelsApiMock.update.mockResolvedValue(updated);
    modelsApiMock.list.mockResolvedValue({ models: [updated] });

    const { result } = renderHook(() => useUpdateModel(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ id: "model-1", patch: { display_name: "Updated Name" } });
    });

    expect(modelsApiMock.update).toHaveBeenCalledWith("model-1", { display_name: "Updated Name" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe("useDeleteModel", () => {
  beforeEach(() => vi.clearAllMocks());

  test("deletes a model and mutation succeeds", async () => {
    modelsApiMock.remove.mockResolvedValue(undefined);
    modelsApiMock.list.mockResolvedValue({ models: [] });

    const { result } = renderHook(() => useDeleteModel(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.mutateAsync("model-1");
    });

    expect(modelsApiMock.remove).toHaveBeenCalledWith("model-1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
