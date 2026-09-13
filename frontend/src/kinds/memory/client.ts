// frontend/src/kinds/memory/client.ts
//
// The shared fetch plumbing for the `memory` kind: auth headers, the typed
// error-envelope check, and the `/api/v1/memory/*` URL builder. Mirrors
// `kinds/knowledge/client.ts` — api.ts is the only importer.

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

/** `/api/v1/memory` — the root every memory route hangs off. */
export const memoryRoot = (): string => `${getCofferBaseUrl()}/memory`;
