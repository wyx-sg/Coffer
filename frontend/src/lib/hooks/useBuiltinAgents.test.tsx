// frontend/src/lib/hooks/useBuiltinAgents.test.tsx — spec 008 US8.
// The built-in agent hooks ride the generic /resources routes for kind
// `builtin_agent`. We mock getApiClient() and assert the verbs are called with
// the right kind/name/body and that errors surface the API envelope message.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import {
  useBuiltinAgents,
  useCreateBuiltinAgent,
  usePatchBuiltinAgent,
  useRemoveBuiltinAgent,
} from "./useBuiltinAgents";
import { mockApiClient } from "@/test/mockApiClient";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const SAMPLE = {
  ref: "builtin_agent:coffer",
  kind: "builtin_agent",
  name: "coffer",
  description: null,
  config: { model: "anthropic:claude-sonnet-4-6", use_gateway: true, confirm_tools: ["*delete*"] },
  enabled: true,
  created_at: "2026-05-28T00:00:00Z",
  updated_at: "2026-05-28T00:00:00Z",
};

describe("useBuiltinAgents", () => {
  beforeEach(() => vi.clearAllMocks());

  test("lists built-in agents with a typed config", async () => {
    const GET = vi.fn().mockResolvedValue({ data: { resources: [SAMPLE] }, error: undefined });
    getApiClientMock.mockReturnValue(
      mockApiClient({ GET }) as unknown as ReturnType<typeof getApiClient>,
    );

    const { result } = renderHook(() => useBuiltinAgents(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(GET).toHaveBeenCalledWith("/resources", {
      params: { query: { kind: "builtin_agent" } },
    });
    expect(result.current.data?.[0].name).toBe("coffer");
    expect(result.current.data?.[0].config.model).toBe("anthropic:claude-sonnet-4-6");
  });

  test("surfaces the API error message on a failed list", async () => {
    const GET = vi.fn().mockResolvedValue({
      data: undefined,
      error: { error: { code: "BOOM", message: "kaboom" } },
    });
    getApiClientMock.mockReturnValue(
      mockApiClient({ GET }) as unknown as ReturnType<typeof getApiClient>,
    );

    const { result } = renderHook(() => useBuiltinAgents(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as Error).message).toContain("kaboom");
  });

  test("create POSTs kind + name + config", async () => {
    const POST = vi.fn().mockResolvedValue({ data: SAMPLE, error: undefined });
    getApiClientMock.mockReturnValue(
      mockApiClient({ POST }) as unknown as ReturnType<typeof getApiClient>,
    );

    const { result } = renderHook(() => useCreateBuiltinAgent(), { wrapper: wrapper() });
    await result.current.mutateAsync({
      name: "coffer",
      config: { model: "anthropic:claude-sonnet-4-6" },
    });

    expect(POST).toHaveBeenCalledWith("/resources", {
      body: {
        kind: "builtin_agent",
        name: "coffer",
        config: { model: "anthropic:claude-sonnet-4-6" },
      },
    });
  });

  test("patch PATCHes the full config to the kind/name path", async () => {
    const PATCH = vi.fn().mockResolvedValue({ data: SAMPLE, error: undefined });
    getApiClientMock.mockReturnValue(
      mockApiClient({ PATCH }) as unknown as ReturnType<typeof getApiClient>,
    );

    const { result } = renderHook(() => usePatchBuiltinAgent(), { wrapper: wrapper() });
    await result.current.mutateAsync({
      name: "coffer",
      config: { model: "openai:gpt-4o", use_gateway: false },
    });

    expect(PATCH).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "builtin_agent", name: "coffer" } },
      body: { config: { model: "openai:gpt-4o", use_gateway: false } },
    });
  });

  test("remove surfaces the last-agent 409 as an ApiError", async () => {
    const DELETE = vi.fn().mockResolvedValue({
      error: {
        error: {
          code: "CANNOT_DELETE_LAST_BUILTIN_AGENT",
          message: "cannot delete the last built-in agent",
        },
      },
    });
    getApiClientMock.mockReturnValue(
      mockApiClient({ DELETE }) as unknown as ReturnType<typeof getApiClient>,
    );

    const { result } = renderHook(() => useRemoveBuiltinAgent(), { wrapper: wrapper() });
    await expect(result.current.mutateAsync("coffer")).rejects.toMatchObject({
      code: "CANNOT_DELETE_LAST_BUILTIN_AGENT",
    });
    expect(DELETE).toHaveBeenCalledWith("/resources/{kind}/{name}", {
      params: { path: { kind: "builtin_agent", name: "coffer" } },
    });
  });
});
