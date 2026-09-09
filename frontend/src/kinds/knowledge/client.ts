// frontend/src/kinds/knowledge/client.ts
//
// The shared fetch plumbing for the `knowledge` kind: auth headers, the typed
// error-envelope check, and the `/api/v1/knowledge[/<scope>]` URL builders.
// Both api.ts (scopes, entries, lanes) and document-api.ts (the document lane)
// import from here rather than from each other, so the two halves of the kind's
// API surface never form an import cycle.

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

export function headers(extra: HeadersInit = {}): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "user",
    ...extra,
  };
}

export async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    // Parse the `{ error: { code, message, details } }` envelope and surface a
    // typed ApiError so `translateApiError(t, …)` can localize it. Mirrors
    // lib/api/fs.ts; a plain Error would leak the raw JSON envelope to users.
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  return r;
}

export const enc = encodeURIComponent;

/** `/api/v1/knowledge` — the collection root (list / create / merge). */
export const knowledgeRoot = (): string => `${getCofferBaseUrl()}/knowledge`;

/** `/api/v1/knowledge/<scope>` — one scope, whatever material it holds. */
export const scopeBase = (scope: string): string => `${knowledgeRoot()}/${enc(scope)}`;
