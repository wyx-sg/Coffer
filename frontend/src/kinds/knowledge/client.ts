// frontend/src/kinds/knowledge/client.ts
//
// The shared fetch plumbing for the `knowledge` kind: auth headers, the typed
// error-envelope check, and the `/api/v1/knowledge/*` URL builder. api.ts is
// the only importer today; it stays split out so the module keeps one concern
// (transport) and the request functions keep the other (routes + shapes).

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

export function headers(extra: HeadersInit = {}): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
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

/** `/api/v1/knowledge` — the root every knowledge route hangs off. */
export const knowledgeRoot = (): string => `${getCofferBaseUrl()}/knowledge`;
