// frontend/src/lib/api/internalEngine.ts — typed fetch for the single, global
// internal-engine model selection (spec 011 amendment 2026-06-22b). The internal
// engine takes its endpoint + key from the `internal_default` connection but its
// MODEL from this singleton.
import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export interface InternalEngineConfig {
  model: string | null;
  updated_at: string | null;
}

async function call<T>(method: "GET" | "PUT", body?: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}/internal-engine-config`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(err?.code ?? "INTERNAL_ERROR", err?.message ?? `request failed: ${r.status}`);
  }
  return data as T;
}

export const internalEngineApi = {
  get: () => call<InternalEngineConfig>("GET"),
  setModel: (model: string | null) => call<InternalEngineConfig>("PUT", { model }),
};
