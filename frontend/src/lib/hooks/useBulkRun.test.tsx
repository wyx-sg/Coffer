// frontend/src/lib/hooks/useBulkRun.test.tsx
//
// useBulkRun sends one request per item, one after another, never stops at a
// failure, returns the failures with their translated reasons, and refreshes
// the lists once, after the last request.
import { describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import "@/i18n";
import { useBulkRun } from "./useBulkRun";
import { ApiError } from "@/lib/api/errors";

describe("useBulkRun", () => {
  test("runs in order, keeps going after a failure and invalidates once at the end", async () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const keys = [["a"], ["b"]];
    const { result } = renderHook(() => useBulkRun(keys), { wrapper });

    const order: string[] = [];
    let running = 0;
    let overlap = false;
    const runOne = async (item: string) => {
      running += 1;
      overlap ||= running > 1;
      order.push(item);
      await Promise.resolve();
      running -= 1;
      if (item === "two") throw new ApiError("INTERNAL_ERROR", "disk full");
    };

    let outcome: Awaited<ReturnType<typeof result.current.run<string>>> | undefined;
    await act(async () => {
      outcome = await result.current.run(["one", "two", "three"], runOne);
    });

    expect(order).toEqual(["one", "two", "three"]);
    expect(overlap).toBe(false);
    expect(outcome?.ok).toBe(2);
    expect(outcome?.failures.map((f) => f.item)).toEqual(["two"]);
    expect(outcome?.failures[0]?.message).toBeTruthy();
    expect(invalidate).toHaveBeenCalledTimes(2);
  });
});
