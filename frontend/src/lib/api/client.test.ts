// What the generated client does when nobody has said where the API is.
//
// Every host but one is served by something: the daemon serves the bundle at
// its own loopback origin, the dev server proxies to it. The desktop shell's
// window is the exception — its document comes from a `tauri://` asset origin
// and the address arrives over IPC a moment later. For that moment the client
// has nowhere to send a request, and what it did with that used to be the
// whole visible bug: it addressed the request to the asset origin, the webview
// refused to build it, and the app rendered "The string did not match the
// expected pattern." on every surface while a healthy daemon served away.
//
// Note where the answer has to come from. The client builds its `Request`
// before any middleware runs, so "no address" cannot be expressed as an empty
// base URL — that throws in the constructor, which is the same crash by
// another route. It is a placeholder that parses plus a middleware that never
// lets a request reach it.
import { afterEach, describe, expect, test, vi } from "vitest";
import { getApiClient, resetApiClient } from "./client";
import { acceptance } from "@/test/acceptance";

const realLocation = window.location;

function servedFrom(origin: string) {
  Object.defineProperty(window, "location", {
    value: { ...realLocation, origin },
    writable: true,
    configurable: true,
  });
}

afterEach(() => {
  Object.defineProperty(window, "location", {
    value: realLocation,
    writable: true,
    configurable: true,
  });
  delete (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__;
  resetApiClient();
  vi.restoreAllMocks();
});

describe("getApiClient", () => {
  acceptance("desktop-app", "a page nobody served does not guess where the API is", async () => {
    servedFrom("tauri://localhost");
    resetApiClient();
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const { error, response } = await getApiClient().GET("/daemon/status");

    // Answered here, not on the wire: nothing was sent anywhere.
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(503);
    // In the daemon's own vocabulary, so the offline banner's "still starting"
    // copy and the errors.DAEMON_NOT_READY translation both apply unchanged.
    expect((error as { error?: { code?: string } } | undefined)?.error?.code).toBe(
      "DAEMON_NOT_READY",
    );
  });

  test("sends the request once a supplier has named the API", async () => {
    servedFrom("tauri://localhost");
    (window as unknown as Record<string, unknown>).__COFFER_BASE_URL__ =
      "http://127.0.0.1:8000/api/v1";
    resetApiClient();
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }));

    await getApiClient().GET("/daemon/status");

    expect(fetchSpy).toHaveBeenCalled();
    const request = fetchSpy.mock.calls[0][0] as Request;
    expect(request.url).toBe("http://127.0.0.1:8000/api/v1/daemon/status");
  });
});
