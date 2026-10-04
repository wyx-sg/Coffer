// frontend/src/lib/api/daemonRestartRequest.ts — `POST /daemon/restart`
// (spec daemon "Restart itself on request"). Kept apart from the polling in
// `lib/daemonRestart.ts`: this is the one request the page sends with its own
// token; everything after it talks to a successor whose token it does not hold.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/daemon";

/** What the daemon answers once its successor is started: the port it binds. */
export type DaemonRestart = components["schemas"]["DaemonRestartOut"];

/** Ask the daemon serving this page to start its successor and exit. */
export function requestDaemonRestart(): Promise<DaemonRestart> {
  return unwrap(getApiClient().POST("/daemon/restart"));
}
