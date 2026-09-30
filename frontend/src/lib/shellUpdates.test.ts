// frontend/src/lib/shellUpdates.test.ts
//
// The page's half of the shell's update check: which command each helper
// invokes, and the "Check automatically" choice the page keeps and reports.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const invokeMock = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

const {
  checkForUpdates,
  followUpdatePreferenceInShell,
  getAutoCheckPreference,
  installUpdate,
  saveAutoCheckPreference,
  setUpdateAutoCheck,
  updatesAvailable,
} = await import("./shellUpdates");

const TAURI_KEY = "__TAURI_INTERNALS__";
const setTauri = (on: boolean) => {
  const w = window as unknown as Record<string, unknown>;
  if (on) w[TAURI_KEY] = {};
  else delete w[TAURI_KEY];
};

describe("shellUpdates", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    localStorage.clear();
  });
  afterEach(() => setTauri(false));

  test("a browser has no update control and reports nothing", () => {
    expect(updatesAvailable()).toBe(false);
    const report = vi.fn().mockResolvedValue(undefined);
    followUpdatePreferenceInShell(report);
    expect(report).not.toHaveBeenCalled();
  });

  test("each action is the shell's own command", async () => {
    setTauri(true);
    invokeMock.mockResolvedValue({});
    await checkForUpdates();
    await installUpdate();
    await setUpdateAutoCheck(false);
    expect(invokeMock.mock.calls).toEqual([
      ["check_for_updates"],
      ["install_update"],
      ["set_update_auto_check", { enabled: false }],
    ]);
  });

  test("the automatic-check choice defaults on and is reported at startup", () => {
    setTauri(true);
    expect(getAutoCheckPreference()).toBe(true);
    saveAutoCheckPreference(false);
    expect(getAutoCheckPreference()).toBe(false);
    const report = vi.fn().mockResolvedValue(undefined);
    followUpdatePreferenceInShell(report);
    expect(report).toHaveBeenCalledWith(false);
  });
});
