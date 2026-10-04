// src/lib/api/daemon.ts — request functions for the daemon's own status, port, residency and upgrade hand-off.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type DaemonStatus = components["schemas"]["DaemonStatusOut"];
export type DaemonPort = components["schemas"]["DaemonPortOut"];
export type DaemonResidency = components["schemas"]["DaemonResidencyOut"];
export type DaemonResidencyIn = components["schemas"]["DaemonResidencyIn"];

export const daemonApi = {
  status: (): Promise<DaemonStatus> => unwrap(getApiClient().GET("/daemon/status")),
  port: (): Promise<DaemonPort> => unwrap(getApiClient().GET("/daemon/port")),
  setPort: (port: number): Promise<DaemonPort> =>
    unwrap(getApiClient().PUT("/daemon/port", { body: { port } })),
  residency: (): Promise<DaemonResidency> => unwrap(getApiClient().GET("/daemon/residency")),
  setResidency: (body: DaemonResidencyIn): Promise<DaemonResidency> =>
    unwrap(getApiClient().PUT("/daemon/residency", { body })),
  /** The prompt that hands an upgrade of Coffer to an agent. */
  upgradePrompt: async (): Promise<string> =>
    (await unwrap(getApiClient().GET("/daemon/upgrade"))).handoff.prompt,
};
