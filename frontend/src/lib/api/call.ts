// frontend/src/lib/api/call.ts
//
// THE hand-written request helper (.agents/frontend.md §4 / §9.1) — every
// `src/lib/api/*` module and every hook that talks to a route outside the
// generated `client.ts` goes through it. It owns URL building against the
// daemon's loopback origin, the `X-Coffer-Token` + `X-Coffer-Actor: "ui"`
// headers every web request carries, 204 handling, and the
// `{error:{code,message,details}}` envelope unwrapped into an `ApiError`.
//
// The only other `fetch` in the app is `lib/chat/streamClient.ts`, which reads
// an SSE body and so cannot share a JSON helper. Do not add a third.
import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface Options {
  method?: Method;
  /**
   * Request body. A plain value is JSON-encoded and sent with
   * `Content-Type: application/json`; a `FormData` is sent as-is with NO
   * Content-Type, so the browser writes the multipart boundary itself.
   * Omitted entirely when undefined, so a bare POST sends none.
   */
  body?: unknown;
}

/**
 * Encode a name/key/path interpolated into a URL path or query string, so a
 * value with URL-significant characters cannot malform or misroute the request
 * (defence in depth — the daemon also constrains names server-side).
 */
export const enc = encodeURIComponent;

/**
 * Call `path` (relative to `/api/v1`) and return its parsed JSON.
 *
 * A 204 resolves to `undefined`, which callers whose route returns nothing
 * type as `call<void>()`. A non-2xx response throws an {@link ApiError}
 * carrying the envelope's `code`, `message` and `details`, falling back to
 * `INTERNAL_ERROR` / `request failed: <status>` when the body is not the
 * envelope (or not JSON at all).
 */
export async function call<T>(path: string, { method = "GET", body }: Options = {}): Promise<T> {
  const headers: Record<string, string> = {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
  };
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  const response = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: isForm ? body : JSON.stringify(body) }),
  });

  if (!response.ok) {
    const envelope = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string; details?: unknown };
    } | null;
    throw new ApiError(
      envelope?.error?.code ?? "INTERNAL_ERROR",
      envelope?.error?.message ?? `request failed: ${response.status}`,
      envelope?.error?.details,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
