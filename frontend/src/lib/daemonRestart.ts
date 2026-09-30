// frontend/src/lib/daemonRestart.ts — restart the daemon from a page it serves.
//
// Spec daemon "Restart itself on request": in a browser the page is served by
// the daemon, so it asks the daemon to restart itself (`POST /daemon/restart`)
// — the daemon starts its successor, answers with the port the successor
// binds, and exits. The page then waits for the new daemon to answer and
// reloads from it: the successor minted a fresh token, which only a newly
// served page carries, and a port saved on Settings → Daemon moves the origin.
//
// Waiting on the same port means waiting for a status probe whose
// `started_at` differs from the one before the restart. On a new port the page
// cannot read another origin's answer, so it waits for that origin to answer
// at all (an opaque `no-cors` probe — no Origin header, so the daemon's own
// Host guard lets it through). Knows nothing about the desktop shell: that
// host restarts through `lib/tauri.ts`.
import { getCofferBaseUrl } from "@/lib/auth";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError, translateApiError } from "@/lib/api/errors";

/** How long the page waits for the successor — the shell's readiness ceiling. */
export const RESTART_READY_TIMEOUT_MS = 90_000;
const POLL_MS = 500;

/** The successor did not answer in time. */
export class RestartTimedOut extends Error {
  constructor() {
    super("the daemon did not come back in time");
    this.name = "RestartTimedOut";
  }
}

/** What a failed restart says, beside the button that asked for it. */
export function restartErrorText(t: (key: string) => string, error: unknown): string {
  return error instanceof RestartTimedOut
    ? t("settings.daemonTab.restartTimedOut")
    : translateApiError(t, error);
}

export interface RestartDeps {
  fetchFn: typeof fetch;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  /** Load the page from `href` (the new daemon serves it with its token). */
  load: (href: string) => void;
  location: Pick<Location, "href" | "origin">;
}

const defaultDeps = (): RestartDeps => ({
  fetchFn: (...args) => fetch(...args),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now: () => Date.now(),
  load: (href) => window.location.assign(href),
  location: window.location,
});

async function startedAt(fetchFn: typeof fetch, origin: string): Promise<string | null> {
  try {
    const r = await fetchFn(`${origin}/api/v1/daemon/status`, { cache: "no-store" });
    if (!r.ok) return null;
    const body = (await r.json()) as { started_at?: string };
    return body.started_at ?? null;
  } catch {
    return null;
  }
}

async function answers(fetchFn: typeof fetch, origin: string): Promise<boolean> {
  try {
    await fetchFn(`${origin}/api/v1/daemon/status`, { mode: "no-cors", cache: "no-store" });
    return true;
  } catch {
    return false;
  }
}

/** Restart the daemon serving this page, wait for its successor, reload from it. */
export async function restartFromBrowser(deps: RestartDeps = defaultDeps()): Promise<void> {
  const { fetchFn, sleep, now, load, location } = deps;
  const daemon = new URL(getCofferBaseUrl() ?? location.origin).origin;
  const before = await startedAt(fetchFn, daemon);

  const { data, error } = await getApiClient().POST("/daemon/restart");
  if (error) throwApiError(error, "INTERNAL_ERROR", "restart failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty restart response");

  const next = new URL(daemon);
  next.port = String(data.port);
  const moved = next.origin !== daemon;
  const deadline = now() + RESTART_READY_TIMEOUT_MS;
  for (;;) {
    await sleep(POLL_MS);
    const ready = moved
      ? await answers(fetchFn, next.origin)
      : await startedAt(fetchFn, daemon).then((at) => at !== null && at !== before);
    if (ready) break;
    if (now() >= deadline) throw new RestartTimedOut();
  }

  // Served by the daemon: follow it to its (possibly new) origin, keeping the
  // page. Anywhere else (the Vite dev server) the page stays where it is and
  // reloads, which asks for the new daemon's address again.
  const page = new URL(location.href);
  if (page.origin === daemon) page.port = next.port;
  load(page.href);
}
