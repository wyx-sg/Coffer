// frontend/src/lib/hooks/useBulkMutate.test.tsx
//
// useBulkMutate fans a per-item op out with Promise.allSettled — so one failing
// item never aborts the rest — then surfaces a single summary toast and runs one
// invalidation burst, resolving with { ok, failed } counts.
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useBulkMutate } from "./useBulkMutate";
import { ToastProvider } from "@/components/ui/toast";

const errorToast = vi.fn();
const successToast = vi.fn();
vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return {
    ...actual,
    useToast: () => ({
      toast: { error: errorToast, success: successToast, info: vi.fn() },
      dismiss: vi.fn(),
    }),
  };
});

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    ),
  };
}

describe("useBulkMutate", () => {
  afterEach(() => vi.clearAllMocks());

  test("a single rejection does not abort the rest (allSettled, not all)", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkMutate(), { wrapper });

    const runOne = vi.fn((n: number) =>
      n === 2 ? Promise.reject(new Error("boom")) : Promise.resolve(),
    );

    let summary: { ok: number; failed: number } | undefined;
    await act(async () => {
      summary = await result.current.run([1, 2, 3], runOne);
    });

    // Every item ran even though item 2 rejected.
    expect(runOne).toHaveBeenCalledTimes(3);
    expect(summary).toEqual({ ok: 2, failed: 1 });
  });

  test("toasts an error summary on partial failure and a success toast when all succeed", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useBulkMutate(), { wrapper });

    await act(async () => {
      await result.current.run([1, 2], (n: number) =>
        n === 1 ? Promise.resolve() : Promise.reject(new Error("x")),
      );
    });
    expect(errorToast).toHaveBeenCalledTimes(1);
    expect(successToast).not.toHaveBeenCalled();

    vi.clearAllMocks();
    await act(async () => {
      await result.current.run([1, 2], () => Promise.resolve());
    });
    expect(successToast).toHaveBeenCalledTimes(1);
    expect(errorToast).not.toHaveBeenCalled();
  });

  test("invalidates the configured query keys once after the batch settles", async () => {
    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useBulkMutate({ invalidate: [["skills"]] }), { wrapper });

    await act(async () => {
      await result.current.run([1, 2, 3], () => Promise.resolve());
    });

    expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["skills"] }));
  });
});
