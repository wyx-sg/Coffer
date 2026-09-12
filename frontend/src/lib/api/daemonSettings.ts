// frontend/src/lib/api/daemonSettings.ts — typed fetch for the daemon's own
// listening port (spec mcp-gateway FR-028).
//
// Hand-written rather than going through the generated client, mirroring
// internalEngine.ts: the port lives in `~/.coffer/daemon-config.json`, read
// before the daemon binds, so it is not a database-backed setting and does not
// follow the settings routes the generated types are kept in step with.
import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

/**
 * The bindable range. Below 1024 needs privileges the daemon deliberately
 * never has, so the UI rejects those before the round-trip — the daemon
 * answers 400 for the same range.
 */
export const MIN_PORT = 1024;
export const MAX_PORT = 65535;

export interface DaemonPortSettings {
  /** The fixed port the user set; null means the daemon picks a free one. */
  configured_port: number | null;
  /** The port the daemon is serving on right now — what a bookmark must use. */
  effective_port: number;
  /** A configured port that differs from the serving one: needs a restart. */
  restart_required: boolean;
}

async function call<T>(method: "GET" | "PUT", body?: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}/settings/daemon`, {
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
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
      err?.details,
    );
  }
  return data as T;
}

export const daemonSettingsApi = {
  get: () => call<DaemonPortSettings>("GET"),
  /** `null` hands the choice back to the daemon's free-port scan. */
  setPort: (port: number | null) => call<DaemonPortSettings>("PUT", { port }),
};
