import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { acceptance } from "@/test/acceptance";
import {
  applyTheme,
  getThemePreference,
  initTheme,
  resolveTheme,
  setThemePreference,
} from "./theme";

type Listener = (event: MediaQueryListEvent) => void;

/** A controllable `prefers-color-scheme: dark` media query. */
function mockSystemDark(initial: boolean) {
  let matches = initial;
  const listeners = new Set<Listener>();
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return matches;
      },
      media: query,
      addEventListener: (_: string, cb: Listener) => listeners.add(cb),
      removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
    })),
  );
  return {
    set(dark: boolean) {
      matches = dark;
      listeners.forEach((cb) => cb({ matches: dark } as MediaQueryListEvent));
    },
  };
}

const html = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  delete html().dataset.theme;
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("resolveTheme", () => {
  it("follows the system only when the preference is system", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("theme preference", () => {
  it("defaults to system and ignores a corrupt stored value", () => {
    expect(getThemePreference()).toBe("system");
    localStorage.setItem("coffer.theme", "sepia");
    expect(getThemePreference()).toBe("system");
  });

  it("falls back to system when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(getThemePreference()).toBe("system");
    vi.restoreAllMocks();
  });
});

acceptance("web-ui", "the theme follows the system appearance live", () => {
  const system = mockSystemDark(false);
  const teardown = initTheme();
  expect(html().dataset.theme).toBe("light");

  system.set(true);
  expect(html().dataset.theme).toBe("dark");
  system.set(false);
  expect(html().dataset.theme).toBe("light");
  teardown();
});

acceptance("web-ui", "a manual theme choice overrides the system and persists", () => {
  const system = mockSystemDark(false);
  const teardown = initTheme();

  setThemePreference("dark");
  expect(html().dataset.theme).toBe("dark");
  expect(localStorage.getItem("coffer.theme")).toBe("dark");

  // The OS flipping no longer moves an explicit choice.
  system.set(false);
  expect(html().dataset.theme).toBe("dark");

  // A reload reads the stored choice back.
  delete html().dataset.theme;
  applyTheme();
  expect(html().dataset.theme).toBe("dark");

  // Back to system: the key is cleared and the OS decides again.
  setThemePreference("system");
  expect(localStorage.getItem("coffer.theme")).toBeNull();
  system.set(true);
  expect(html().dataset.theme).toBe("dark");
  teardown();
});
