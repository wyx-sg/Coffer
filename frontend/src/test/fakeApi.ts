// frontend/src/test/fakeApi.ts
//
// A fake daemon for suites that drive the typed client (`getApiClient()`) end
// to end, so the request modules, the hooks and the query cache all stay real
// and only the network boundary is faked.
//
// The typed client calls `fetch(Request)`. This helper installs one stable
// `fetch` on `globalThis` (the client captures `fetch` when it is first built,
// so it must exist before any request is made — import this module first) and
// forwards every request to a `vi.fn()` shaped like the old hand-written
// `call(path, { method, body })`:
//
//   const call = fakeApi();                  // module scope
//   beforeEach(() => call.mockReset());
//   call.mockImplementation(async (path, opts) => { … return body; });
//
// `path` is relative to `/api/v1` and keeps its query string; `opts.method` is
// always set and `opts.body` is the parsed JSON body (absent when none was
// sent). Return a value to answer 200 with it, or `undefined` to answer 204.
// Throw an `ApiError` to answer with that error envelope (status 400, or the
// `status` on the error when it has one); throw any other error to make the
// request itself fail, as a dropped connection does.
import { vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

interface FakeCallOptions {
  method: string;
  body?: unknown;
  signal?: AbortSignal;
}

export type FakeCall = import("vitest").Mock<(path: string, opts: FakeCallOptions) => unknown>;

const API_PREFIX = "/api/v1";
const call: FakeCall = vi.fn();

async function answer(input: Request | string | URL, init?: RequestInit): Promise<Response> {
  const request = input instanceof Request ? input : new Request(input, init);
  const url = new URL(request.url);
  const path =
    (url.pathname.startsWith(API_PREFIX) ? url.pathname.slice(API_PREFIX.length) : url.pathname) +
    url.search;
  const opts: FakeCallOptions = { method: request.method, signal: request.signal };
  const text = ["GET", "HEAD"].includes(request.method) ? "" : await request.clone().text();
  if (text !== "") {
    try {
      opts.body = JSON.parse(text);
    } catch {
      opts.body = text;
    }
  }
  let result: unknown;
  try {
    result = await call(path, opts);
  } catch (e) {
    if (!(e instanceof ApiError)) throw e;
    const status = (e as ApiError & { status?: number }).status ?? 400;
    return new Response(
      JSON.stringify({ error: { code: e.code, message: e.envelopeMessage, details: e.details } }),
      { status, headers: { "Content-Type": "application/json" } },
    );
  }
  if (result === undefined) return new Response(null, { status: 204 });
  return new Response(JSON.stringify(result), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

globalThis.fetch = ((input: Request | string | URL, init?: RequestInit) =>
  answer(input, init)) as typeof fetch;

/** The fake's `call` mock: set its implementation and assert on `mock.calls`. */
export function fakeApi(): FakeCall {
  return call;
}
