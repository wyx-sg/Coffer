// frontend/src/lib/api/call.ts
//
// The one hand-written request helper (agents/frontend.md §4 / §9.1): URL
// building against the daemon's loopback origin, the `X-Coffer-Token` +
// `X-Coffer-Actor: "ui"` headers every web request carries, 204 handling, and
// the `{error:{code,message}}` envelope unwrapped into an `ApiError`.
//
// It exists so a module needing a hand-written client does not copy the helper
// a fifth time. `api/chat.ts`, `agents.ts`, `providers.ts`, `skills.ts` and `channels.ts` still
// own their own copies; migrate one when you touch it.
import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface Options {
  method?: Method;
  /** JSON request body. Omitted entirely when undefined, so a bare POST sends none. */
  body?: unknown;
}

/**
 * Call `path` (relative to `/api/v1`) and return its parsed JSON.
 *
 * A 204 resolves to `undefined`, which callers whose route returns nothing
 * type as `call<void>()`.
 */
export async function call<T>(path: string, { method = "GET", body }: Options = {}): Promise<T> {
  const headers: Record<string, string> = {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
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
