// frontend/src/lib/tauri.test.ts
//
// Tauri context detection + command-invocation helpers. Outside a Tauri
// WebView (i.e. in vitest/jsdom) the helpers must return safe fallbacks or
// throw; inside Tauri they must `invoke()` the matching command. We exercise
// both branches by toggling the `__TAURI_INTERNALS__` sentinel and mocking the
// dynamically-imported `@tauri-apps/api/core` module.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  isTauri,
  getDaemonInfo,
  getAutostartEnabled,
  setAutostartEnabled,
  restartDaemon,
} from "./tauri";

// `@tauri-apps/api/core` is dynamically imported inside each helper. We stub it
// with a shared `invoke` mock so we can assert command name + args.
const invokeMock = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

const TAURI_KEY = "__TAURI_INTERNALS__";

function enterTauri() {
  (window as unknown as Record<string, unknown>)[TAURI_KEY] = {};
}

function leaveTauri() {
  delete (window as unknown as Record<string, unknown>)[TAURI_KEY];
}

describe("isTauri", () => {
  afterEach(() => leaveTauri());

  test("false when the Tauri sentinel is absent (browser/jsdom)", () => {
    leaveTauri();
    expect(isTauri()).toBe(false);
  });

  test("true once the Tauri internals sentinel is injected", () => {
    enterTauri();
    expect(isTauri()).toBe(true);
  });
});

describe("getDaemonInfo", () => {
  beforeEach(() => invokeMock.mockReset());
  afterEach(() => leaveTauri());

  test("throws outside Tauri instead of invoking", async () => {
    leaveTauri();
    await expect(getDaemonInfo()).rejects.toThrow(/only available inside the Tauri app/i);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  test("invokes get_daemon_info and returns its connection info inside Tauri", async () => {
    enterTauri();
    const info = { baseUrl: "http://127.0.0.1:9001/api/v1", token: "tok" };
    invokeMock.mockResolvedValue(info);
    await expect(getDaemonInfo()).resolves.toEqual(info);
    expect(invokeMock).toHaveBeenCalledWith("get_daemon_info");
  });
});

describe("setAutostartEnabled", () => {
  beforeEach(() => invokeMock.mockReset());
  afterEach(() => leaveTauri());

  test("dev fallback echoes the requested flag without invoking", async () => {
    leaveTauri();
    await expect(setAutostartEnabled(true)).resolves.toBe(true);
    await expect(setAutostartEnabled(false)).resolves.toBe(false);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  test("invokes set_autostart_enabled with the flag inside Tauri", async () => {
    enterTauri();
    invokeMock.mockResolvedValue(true);
    await expect(setAutostartEnabled(true)).resolves.toBe(true);
    expect(invokeMock).toHaveBeenCalledWith("set_autostart_enabled", { enabled: true });
  });
});

describe("getAutostartEnabled", () => {
  beforeEach(() => invokeMock.mockReset());
  afterEach(() => leaveTauri());

  test("returns false outside Tauri without invoking", async () => {
    leaveTauri();
    await expect(getAutostartEnabled()).resolves.toBe(false);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  test("invokes get_autostart_enabled inside Tauri", async () => {
    enterTauri();
    invokeMock.mockResolvedValue(true);
    await expect(getAutostartEnabled()).resolves.toBe(true);
    expect(invokeMock).toHaveBeenCalledWith("get_autostart_enabled");
  });
});

describe("restartDaemon", () => {
  beforeEach(() => invokeMock.mockReset());
  afterEach(() => leaveTauri());

  test("throws outside Tauri instead of invoking", async () => {
    leaveTauri();
    await expect(restartDaemon()).rejects.toThrow(/only available inside the Tauri app/i);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  test("invokes restart_daemon and returns the spawn result inside Tauri", async () => {
    enterTauri();
    const result = { pid: 4242, started: true };
    invokeMock.mockResolvedValue(result);
    await expect(restartDaemon()).resolves.toEqual(result);
    expect(invokeMock).toHaveBeenCalledWith("restart_daemon");
  });
});
