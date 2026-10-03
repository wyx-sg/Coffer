import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

let emit: (full: boolean) => void = () => {};
const stop = vi.fn();
vi.mock("@/lib/windowFullscreen", () => ({
  watchWindowFullscreen: (cb: (full: boolean) => void) => {
    emit = cb;
    return stop;
  },
}));

import { useWindowFullscreen } from "./useWindowFullscreen";

describe("useWindowFullscreen", () => {
  beforeEach(() => stop.mockClear());

  test("follows the window's full-screen state and unsubscribes on unmount", () => {
    const { result, unmount } = renderHook(() => useWindowFullscreen());
    expect(result.current).toBe(false);
    act(() => emit(true));
    expect(result.current).toBe(true);
    act(() => emit(false));
    expect(result.current).toBe(false);
    unmount();
    expect(stop).toHaveBeenCalled();
  });
});
