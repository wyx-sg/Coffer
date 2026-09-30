// The browser's restart (spec daemon "Restart itself on request"): ask the
// daemon to restart itself, wait for its successor, reload from it. The api
// client, fetch, the clock and the page load are all fakes.
import { beforeEach, describe, expect, test, vi } from "vitest";

import { acceptance } from "@/test/acceptance";

const post = vi.fn();
vi.mock("@/lib/api/client", () => ({ getApiClient: () => ({ POST: post }) }));
vi.mock("@/lib/auth", () => ({ getCofferBaseUrl: () => "http://127.0.0.1:8000/api/v1" }));

const { restartFromBrowser, RestartTimedOut, RESTART_READY_TIMEOUT_MS, restartErrorText } =
  await import("./daemonRestart");

function deps(fetchFn: typeof fetch, href = "http://127.0.0.1:8000/settings/daemon") {
  let now = 0;
  const load = vi.fn();
  return {
    load,
    deps: {
      fetchFn,
      sleep: async (ms: number) => {
        now += ms;
      },
      now: () => now,
      load,
      location: { href, origin: new URL(href).origin },
    },
  };
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

beforeEach(() => post.mockReset());

describe("restartFromBrowser", () => {
  acceptance("web-ui", "a browser restarts the daemon from the daemon tab", async () => {
    post.mockResolvedValue({ data: { port: 8000 } });
    // The old daemon answers, goes away, then its successor answers with a new start time.
    const answers = [
      json({ started_at: "old" }),
      json({ started_at: "old" }),
      new TypeError("connection refused"),
      json({ started_at: "new" }),
    ];
    const fetchFn = vi.fn(async () => {
      const next = answers.shift() ?? json({ started_at: "new" });
      if (next instanceof Error) throw next;
      return next;
    }) as unknown as typeof fetch;
    const { deps: d, load } = deps(fetchFn);

    await restartFromBrowser(d);

    expect(post).toHaveBeenCalledWith("/daemon/restart");
    expect(load).toHaveBeenCalledWith("http://127.0.0.1:8000/settings/daemon");
  });

  test("a restart onto a saved port reloads the page from the new origin", async () => {
    post.mockResolvedValue({ data: { port: 8123 } });
    const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("http://127.0.0.1:8123")) {
        expect(init?.mode).toBe("no-cors");
        return new Response(null, { status: 200 });
      }
      return json({ started_at: "old" });
    }) as unknown as typeof fetch;
    const { deps: d, load } = deps(fetchFn);

    await restartFromBrowser(d);

    expect(load).toHaveBeenCalledWith("http://127.0.0.1:8123/settings/daemon");
  });

  test("a successor that never answers times out and loads nothing", async () => {
    post.mockResolvedValue({ data: { port: 8000 } });
    const fetchFn = vi.fn(async () => json({ started_at: "old" })) as unknown as typeof fetch;
    const { deps: d, load } = deps(fetchFn);

    await expect(restartFromBrowser(d)).rejects.toBeInstanceOf(RestartTimedOut);
    expect(load).not.toHaveBeenCalled();
    expect(RESTART_READY_TIMEOUT_MS).toBe(90_000);
    expect(restartErrorText((k) => k, new RestartTimedOut())).toBe(
      "settings.daemonTab.restartTimedOut",
    );
  });

  test("a refused restart throws before waiting", async () => {
    post.mockResolvedValue({
      error: { error: { code: "INTERNAL_ERROR", message: "could not start" } },
    });
    const fetchFn = vi.fn(async () => json({ started_at: "old" })) as unknown as typeof fetch;
    const { deps: d, load } = deps(fetchFn);

    await expect(restartFromBrowser(d)).rejects.toThrow();
    expect(load).not.toHaveBeenCalled();
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });
});
