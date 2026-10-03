import { afterEach, describe, expect, test, vi } from "vitest";

import { watchWindowFullscreen } from "./windowFullscreen";

function size(width: number, height: number) {
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(width);
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(height);
}

describe("watchWindowFullscreen", () => {
  afterEach(() => vi.restoreAllMocks());

  test("a window covering the screen is full screen; a zoomed one leaving the menu bar is not", () => {
    vi.spyOn(window.screen, "width", "get").mockReturnValue(1512);
    vi.spyOn(window.screen, "height", "get").mockReturnValue(982);
    size(1512, 949);
    const seen: boolean[] = [];
    const stop = watchWindowFullscreen((full) => seen.push(full));
    size(1512, 982);
    window.dispatchEvent(new Event("resize"));
    stop();
    size(1512, 949);
    window.dispatchEvent(new Event("resize"));
    expect(seen).toEqual([false, true]);
  });
});
