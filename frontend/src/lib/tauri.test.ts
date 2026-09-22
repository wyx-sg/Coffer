// frontend/src/lib/tauri.test.ts
//
// The same bundle runs in a browser and in the desktop shell, so every helper
// here has two behaviours and both matter. Outside a Tauri WebView (i.e. in
// vitest/jsdom, standing in for the browser host) they must return a safe
// fallback or throw rather than reach for an IPC that isn't there; inside one
// they must `invoke()` the matching command. We exercise both branches by
// toggling the `__TAURI_INTERNALS__` sentinel and mocking the
// dynamically-imported `@tauri-apps/api/core` module.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  isTauri,
  getDaemonInfo,
  connectToShellDaemon,
  credentialDesktopHost,
  handshakeRetryDelay,
  HANDSHAKE_RETRY_DELAYS_MS,
  restartDaemon,
  daemonVersionMatches,
} from "./tauri";
import { getCofferBaseUrl, getCofferToken } from "./auth";
import { getApiClient, resetApiClient } from "./api/client";
import { acceptance } from "@/test/acceptance";

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
    const info = { baseUrl: "http://127.0.0.1:8000/api/v1", token: "tok" };
    invokeMock.mockResolvedValue(info);
    await expect(getDaemonInfo()).resolves.toEqual(info);
    expect(invokeMock).toHaveBeenCalledWith("get_daemon_info");
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

describe("daemonVersionMatches", () => {
  beforeEach(() => invokeMock.mockReset());
  afterEach(() => leaveTauri());

  test("reports a match outside Tauri without invoking — a browser has no pairing", async () => {
    leaveTauri();
    await expect(daemonVersionMatches("0.0.1")).resolves.toBe(true);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  test("invokes daemon_version_matches with the reported version inside Tauri", async () => {
    enterTauri();
    invokeMock.mockResolvedValue(false);
    await expect(daemonVersionMatches("0.1.0")).resolves.toBe(false);
    expect(invokeMock).toHaveBeenCalledWith("daemon_version_matches", {
      daemonVersion: "0.1.0",
    });
  });
});

describe("connectToShellDaemon", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    resetApiClient();
  });

  afterEach(() => {
    leaveTauri();
    const w = window as unknown as Record<string, unknown>;
    delete w.__COFFER_BASE_URL__;
    delete w.__COFFER_TOKEN__;
  });

  acceptance("desktop-app", "the handshake credentials a locally-hosted page", async () => {
    enterTauri();
    invokeMock.mockResolvedValue({ baseUrl: "http://127.0.0.1:8000/api/v1", token: "fresh-token" });

    await connectToShellDaemon();

    // Read back through the ordinary getters: nothing downstream should be
    // able to tell which host supplied the credentials.
    expect(getCofferBaseUrl()).toBe("http://127.0.0.1:8000/api/v1");
    expect(getCofferToken()).toBe("fresh-token");
  });

  test("drops the memoised API client, which captured the pre-handshake base URL", async () => {
    enterTauri();
    // A client built before the handshake holds the same-origin fallback — for
    // the desktop host an asset origin with no daemon behind it. Forgetting
    // this reset is the bug that makes every request go nowhere.
    const staleClient = getApiClient();
    invokeMock.mockResolvedValue({ baseUrl: "http://127.0.0.1:8000/api/v1", token: "tok" });

    await connectToShellDaemon();

    expect(getApiClient()).not.toBe(staleClient);
  });

  test("propagates the IPC failure and leaves the previous credentials alone", async () => {
    enterTauri();
    invokeMock.mockRejectedValue(new Error("coffer-daemon did not become ready within 90s"));

    await expect(connectToShellDaemon()).rejects.toThrow(/did not become ready/);
    // Callers want different things from a failure, so it is re-thrown rather
    // than swallowed — and a half-applied handshake would be worse than none.
    expect(getCofferToken()).toBeNull();
  });
});

describe("credentialDesktopHost", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    resetApiClient();
  });

  afterEach(() => {
    leaveTauri();
    const w = window as unknown as Record<string, unknown>;
    delete w.__COFFER_BASE_URL__;
    delete w.__COFFER_TOKEN__;
  });

  test("does nothing outside Tauri — the browser hosts are already credentialed", async () => {
    leaveTauri();
    const connect = vi.fn();
    await credentialDesktopHost(vi.fn(), { connect });
    expect(connect).not.toHaveBeenCalled();
  });

  acceptance("desktop-app", "a handshake that misses is retried until it lands", async () => {
    enterTauri();
    // The shape of the bug: the daemon is a few seconds from serving, so the
    // first attempts time out. Nothing about that should be permanent.
    const connect = vi
      .fn()
      .mockRejectedValueOnce(new Error("coffer-daemon did not become ready within 90s"))
      .mockRejectedValueOnce(new Error("coffer-daemon did not become ready within 90s"))
      .mockResolvedValueOnce(undefined);
    const waited: number[] = [];
    const onConnected = vi.fn();

    await credentialDesktopHost(onConnected, {
      connect,
      wait: (ms) => {
        waited.push(ms);
        return Promise.resolve();
      },
    });

    expect(connect).toHaveBeenCalledTimes(3);
    // …and the page is repaired the moment one lands, with no user action.
    expect(onConnected).toHaveBeenCalledTimes(1);
    // Backing off rather than hammering: a daemon that is still unpacking
    // itself is not helped by being asked again immediately.
    expect(waited).toEqual([HANDSHAKE_RETRY_DELAYS_MS[0], HANDSHAKE_RETRY_DELAYS_MS[1]]);
  });

  test("stops asking once a connection lands", async () => {
    enterTauri();
    const connect = vi.fn().mockResolvedValue(undefined);
    const wait = vi.fn().mockResolvedValue(undefined);

    await credentialDesktopHost(vi.fn(), { connect, wait });

    expect(connect).toHaveBeenCalledTimes(1);
    expect(wait).not.toHaveBeenCalled();
  });
});

describe("handshakeRetryDelay", () => {
  test("backs off, then settles on the last delay forever", () => {
    expect(handshakeRetryDelay(1)).toBe(HANDSHAKE_RETRY_DELAYS_MS[0]);
    expect(handshakeRetryDelay(2)).toBe(HANDSHAKE_RETRY_DELAYS_MS[1]);
    const last = HANDSHAKE_RETRY_DELAYS_MS[HANDSHAKE_RETRY_DELAYS_MS.length - 1];
    expect(handshakeRetryDelay(HANDSHAKE_RETRY_DELAYS_MS.length)).toBe(last);
    // There is no attempt after which the app gives up, so there is no
    // attempt number without a delay.
    expect(handshakeRetryDelay(999)).toBe(last);
  });
});
