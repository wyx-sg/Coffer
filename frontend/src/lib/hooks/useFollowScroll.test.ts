// frontend/src/lib/hooks/useFollowScroll.test.ts
import { describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useFollowScroll } from "./useFollowScroll";

function setup(
  initial: { resetKey?: string; isStreaming?: boolean; contentVersion?: unknown } = {},
) {
  const scrollIntoView = vi.fn();
  const bottom = { scrollIntoView } as unknown as HTMLElement;
  // A 1000px-tall scroll area showing 300px; scrollTop decides "near bottom".
  const scrollEl = { scrollHeight: 1000, clientHeight: 300, scrollTop: 700 } as HTMLElement;
  const scrollRef = { current: scrollEl };
  const bottomRef = { current: bottom };
  const hook = renderHook(
    (props: { resetKey: string; isStreaming: boolean; contentVersion: unknown }) =>
      useFollowScroll({ scrollRef, bottomRef, ...props }),
    {
      initialProps: {
        resetKey: initial.resetKey ?? "conv-1",
        isStreaming: initial.isStreaming ?? false,
        contentVersion: initial.contentVersion ?? 0,
      },
    },
  );
  return { ...hook, scrollIntoView, scrollEl };
}

describe("useFollowScroll", () => {
  test("starts following and lands at the bottom", () => {
    const { result, scrollIntoView } = setup();
    expect(result.current.following).toBe(true);
    expect(scrollIntoView).toHaveBeenCalled();
  });

  test("new content scrolls while following; instantly during streaming, smoothly otherwise", () => {
    const { rerender, scrollIntoView } = setup();
    scrollIntoView.mockClear();
    rerender({ resetKey: "conv-1", isStreaming: true, contentVersion: 1 });
    expect(scrollIntoView).toHaveBeenLastCalledWith({ behavior: "auto" });
    rerender({ resetKey: "conv-1", isStreaming: false, contentVersion: 2 });
    expect(scrollIntoView).toHaveBeenLastCalledWith({ behavior: "smooth" });
  });

  test("scrolling up detaches: new content no longer scrolls; jumpToLatest re-attaches", () => {
    const { result, rerender, scrollIntoView, scrollEl } = setup();
    scrollEl.scrollTop = 0;
    act(() => result.current.onScroll());
    expect(result.current.following).toBe(false);

    scrollIntoView.mockClear();
    rerender({ resetKey: "conv-1", isStreaming: true, contentVersion: 1 });
    expect(scrollIntoView).not.toHaveBeenCalled();

    act(() => result.current.jumpToLatest());
    expect(result.current.following).toBe(true);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
  });

  test("opening another thread restarts at the bottom even when detached", () => {
    const { result, rerender, scrollIntoView, scrollEl } = setup();
    scrollEl.scrollTop = 0;
    act(() => result.current.onScroll());
    expect(result.current.following).toBe(false);

    scrollIntoView.mockClear();
    rerender({ resetKey: "conv-2", isStreaming: false, contentVersion: 0 });
    expect(result.current.following).toBe(true);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "auto" });
  });
});
