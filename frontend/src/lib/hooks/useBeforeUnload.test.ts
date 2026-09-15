// frontend/src/lib/hooks/useBeforeUnload.test.ts
import { describe, expect, test } from "vitest";
import { renderHook } from "@testing-library/react";

import { useBeforeUnload } from "./useBeforeUnload";

function fireBeforeUnload(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("useBeforeUnload", () => {
  test("blocks unload while enabled", () => {
    renderHook(() => useBeforeUnload(true));
    expect(fireBeforeUnload()).toBe(true);
  });

  test("does nothing while disabled", () => {
    renderHook(() => useBeforeUnload(false));
    expect(fireBeforeUnload()).toBe(false);
  });

  test("follows the flag as it changes and detaches on unmount", () => {
    const { rerender, unmount } = renderHook(({ on }: { on: boolean }) => useBeforeUnload(on), {
      initialProps: { on: true },
    });
    expect(fireBeforeUnload()).toBe(true);
    rerender({ on: false });
    expect(fireBeforeUnload()).toBe(false);
    rerender({ on: true });
    expect(fireBeforeUnload()).toBe(true);
    unmount();
    expect(fireBeforeUnload()).toBe(false);
  });
});
