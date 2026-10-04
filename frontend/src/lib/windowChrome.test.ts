import { afterEach, describe, expect, test, vi } from "vitest";

const shell = vi.hoisted(() => ({ inShell: false }));
vi.mock("./tauri", () => ({ inDesktopShell: () => shell.inShell }));

import { applyWindowChrome, overlayTitleBar } from "./windowChrome";

function setPlatform(platform: string) {
  Object.defineProperty(navigator, "platform", { configurable: true, value: platform });
}

afterEach(() => {
  delete document.documentElement.dataset.chrome;
  shell.inShell = false;
  setPlatform("");
});

describe("window chrome", () => {
  test("the macOS shell draws the title bar as an overlay", () => {
    shell.inShell = true;
    setPlatform("MacIntel");
    expect(overlayTitleBar()).toBe(true);
    applyWindowChrome();
    expect(document.documentElement.dataset.chrome).toBe("overlay");
  });

  test("a browser tab gets no inset", () => {
    setPlatform("MacIntel");
    applyWindowChrome();
    expect(overlayTitleBar()).toBe(false);
    expect(document.documentElement.dataset.chrome).toBeUndefined();
  });

  test("the Windows and Linux shells keep their native title bar", () => {
    shell.inShell = true;
    setPlatform("Win32");
    applyWindowChrome();
    expect(overlayTitleBar()).toBe(false);
    expect(document.documentElement.dataset.chrome).toBeUndefined();
  });
});
