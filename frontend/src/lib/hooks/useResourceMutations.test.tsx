// frontend/src/lib/hooks/useResourceMutations.test.tsx
//
// The kind-agnostic writes. Every one of them is addressed by the resource's
// UID alone — the `{kind}` segment is gone from these routes — while `kind`
// still rides along in the hook's input, purely to pick which of the per-kind
// list keys `onSuccess` refreshes. The tests below assert that split directly:
// the uid in the path, the kind nowhere near it.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import {
  useEnableResource,
  useDisableResource,
  useDeleteResource,
  useRenameResource,
} from "./useResourceMutations";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

/** Uids of the resources under test, alongside the labels they happen to wear.
 *  Nothing here makes the two equal: a hook that sent the name instead of the
 *  uid has to fail these, not coincide with them. */
const FS_UID = "u-mcp-9f2c"; // named "fs"
const GITHUB_UID = "u-mcp-be04"; // named "github"
const WRITING_UID = "u-skill-4e8d"; // named "writing"
const OLD_UID = "u-mcp-0a13"; // named "old-server"

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    qc,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  };
}

describe("useEnableResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("POSTs to the enable endpoint addressed by uid alone", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", uid: FS_UID });
    });

    // The kind the caller passed is NOT in the path: a uid already names
    // exactly one row, and a second segment would only be a second way to get
    // it wrong.
    expect(postMock).toHaveBeenCalledWith(
      "/resources/{uid}/enable",
      expect.objectContaining({ params: { path: { uid: FS_UID } } }),
    );
  });

  test("invalidates the resources query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", uid: FS_UID });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
  });

  test("also invalidates the kind's own query key, so kind-owned surfaces refresh", async () => {
    // The skill detail page reads ["skills", uid], not the generic resource
    // list — invalidating only ["resources"] left its activation control
    // rendering the pre-toggle state after a successful disable. This is the
    // whole reason `kind` is an input to a request that does not carry it.
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "skill", uid: WRITING_UID });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["skills"] }));
  });

  test("surfaces ApiError when POST fails so translateApiError can resolve the code", async () => {
    getApiClientMock.mockReturnValue({
      POST: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "RESOURCE_NOT_FOUND", message: "not found" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnableResource(), { wrapper });

    await act(async () => {
      try {
        await result.current.mutateAsync({ kind: "mcp_server", uid: FS_UID });
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("RESOURCE_NOT_FOUND");
    expect(err.message).toContain("not found");
  });
});

describe("useDisableResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("POSTs to the disable endpoint", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDisableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", uid: GITHUB_UID });
    });

    expect(postMock).toHaveBeenCalledWith(
      "/resources/{uid}/disable",
      expect.objectContaining({ params: { path: { uid: GITHUB_UID } } }),
    );
  });

  test("invalidates the resources query key on success", async () => {
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({ POST: postMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useDisableResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", uid: GITHUB_UID });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
  });
});

describe("useDeleteResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("sends DELETE to the uid's own route", async () => {
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({ DELETE: deleteMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDeleteResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", uid: OLD_UID });
    });

    expect(deleteMock).toHaveBeenCalledWith(
      "/resources/{uid}",
      expect.objectContaining({ params: { path: { uid: OLD_UID } } }),
    );
  });

  test("invalidates resources query on success", async () => {
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({ DELETE: deleteMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useDeleteResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "mcp_server", uid: OLD_UID });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
  });
});

describe("useRenameResource", () => {
  beforeEach(() => vi.clearAllMocks());

  test("PATCHes the uid's route with the new label", async () => {
    // A rename is an ordinary field edit now, not an operation: the same PATCH
    // that would change a description, and the same route for every kind. The
    // uid in the path is what makes that safe — the thing being renamed is
    // still named the same way after the rename lands.
    const patchMock = vi
      .fn()
      .mockResolvedValue({ data: { uid: WRITING_UID, name: "drafting" }, error: undefined });
    getApiClientMock.mockReturnValue({ PATCH: patchMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRenameResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "skill", uid: WRITING_UID, name: "drafting" });
    });

    expect(patchMock).toHaveBeenCalledWith(
      "/resources/{uid}",
      expect.objectContaining({
        params: { path: { uid: WRITING_UID } },
        body: { name: "drafting" },
      }),
    );
  });

  test("refreshes the generic list and the kind's own key", async () => {
    const patchMock = vi
      .fn()
      .mockResolvedValue({ data: { uid: WRITING_UID, name: "drafting" }, error: undefined });
    getApiClientMock.mockReturnValue({ PATCH: patchMock } as unknown as ReturnType<
      typeof getApiClient
    >);

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useRenameResource(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ kind: "skill", uid: WRITING_UID, name: "drafting" });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["resources"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["skills"] }));
  });

  test("a taken label surfaces as a 409 ApiError for the form to render", async () => {
    // Deliberately NOT a toast: the only way to rename is a form with a name
    // field in it, and that is where the failure belongs — beside the field
    // the user can correct.
    getApiClientMock.mockReturnValue({
      PATCH: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "RESOURCE_EXISTS", message: "name already in use" } },
      }),
    } as unknown as ReturnType<typeof getApiClient>);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRenameResource(), { wrapper });

    await act(async () => {
      try {
        await result.current.mutateAsync({ kind: "skill", uid: WRITING_UID, name: "reviewing" });
      } catch {
        // expected
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("RESOURCE_EXISTS");
  });
});
