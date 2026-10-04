import createClient from "openapi-fetch";
import type { paths } from "./types";
import { getCofferToken, getCofferBaseUrl } from "../auth";
import { ApiError, daemonNotReadyResponse, throwApiError } from "./errors";

let _client: ReturnType<typeof createClient<paths>> | null = null;

/**
 * The base URL a client built before anyone named one carries.
 *
 * It is never called: the middleware below answers every request while this is
 * the address. It exists because the client builds a `Request` **before** any
 * middleware runs, so the placeholder has to be something the runtime can
 * parse — an empty base URL leaves a bare path, and a path with nothing to
 * resolve against throws inside the constructor, which is precisely the crash
 * that used to surface as "The string did not match the expected pattern." on
 * every page of the desktop app. `.invalid` is reserved by RFC 2606 and
 * resolves nowhere, so even a request that somehow escaped the middleware
 * would reach nothing rather than something.
 */
const UNSUPPLIED_BASE_URL = "http://daemon-not-supplied.invalid/api/v1";

export function getApiClient(): ReturnType<typeof createClient<paths>> {
  if (_client !== null) return _client;
  const client = createClient<paths>({
    baseUrl: getCofferBaseUrl() ?? UNSUPPLIED_BASE_URL,
    headers: { "X-Coffer-Actor": "ui" },
  });
  // Read the token fresh on every request via middleware rather than
  // capturing it at client-creation time. A token that arrives after the
  // first request (e.g. injected post-mount by a test or the dev plugin) is
  // then picked up automatically — no resetApiClient() / page reload needed.
  client.use({
    onRequest({ request }) {
      // Still nobody to call: this client was built with the placeholder
      // above, so answer here rather than let the request leave. A base URL
      // that arrives later rebuilds the client (`resetApiClient`), so this
      // branch cannot outlive the gap it describes.
      if (getCofferBaseUrl() === null) return daemonNotReadyResponse();
      request.headers.set("X-Coffer-Token", getCofferToken() ?? "");
      return request;
    },
  });
  _client = client;
  return _client;
}

/** Drop the memoised client (e.g. if the base URL changes). */
export function resetApiClient(): void {
  _client = null;
}

/** What every openapi-fetch method settles to (success carries `data`, a non-2xx carries `error`). */
interface Settled<D> {
  data?: D;
  error?: unknown;
  response: Response;
}

type Envelope = Parameters<typeof throwApiError>[0];

function raise(result: Settled<unknown>): never {
  return throwApiError(
    result.error as Envelope,
    "INTERNAL_ERROR",
    `request failed: ${result.response?.status}`,
    result.response,
  );
}

/**
 * Settle a typed-client call to its 2xx body. openapi-fetch returns a non-2xx
 * as `{ error }` instead of throwing, so every request function goes through
 * one of the three `unwrap*` helpers: a non-2xx throws an {@link ApiError}
 * carrying the envelope's `code`, `message` and `details`, and a network
 * failure rejects as `fetch` does. A route that answers 200 always has a body;
 * an empty one is a contract break, not a value.
 */
export async function unwrap<D>(call: Promise<Settled<D>>): Promise<D> {
  const result = await call;
  if (result.error !== undefined) raise(result);
  if (result.data === undefined) {
    throw new ApiError("INTERNAL_ERROR", `empty response: ${result.response?.status}`);
  }
  return result.data;
}

/** Settle a call whose route answers with no body (204), or whose body is not read. */
export async function unwrapVoid(call: Promise<Settled<unknown>>): Promise<void> {
  const result = await call;
  if (result.error !== undefined) raise(result);
}

/** Settle a call whose route answers 200 with a body or 204 with none. */
export async function unwrapOptional<D>(call: Promise<Settled<D>>): Promise<D | undefined> {
  const result = await call;
  if (result.error !== undefined) raise(result);
  return result.data;
}
