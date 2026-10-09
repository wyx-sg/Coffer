// src/lib/api/daemon.ts — request functions for the daemon's own status, port, residency, setup check and upgrade hand-off.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type DaemonStatus = components["schemas"]["DaemonStatusOut"];
export type DaemonPort = components["schemas"]["DaemonPortOut"];
export type DaemonResidency = components["schemas"]["DaemonResidencyOut"];
export type DaemonResidencyIn = components["schemas"]["DaemonResidencyIn"];
/** What a daemon in its setup state waits for (spec daemon "Wait in a setup state when git is missing or too old"). */
export type DaemonSetup = components["schemas"]["DaemonSetupOut"];
export type DaemonSetupCheck = components["schemas"]["DaemonSetupCheckOut"];
/** How this Coffer is upgraded, and what the daemon's own release check found
 *  (spec daemon "Check the installed binaries for a new release"). */
export type DaemonUpgrade = components["schemas"]["DaemonUpgradeOut"];

export const daemonApi = {
  status: (): Promise<DaemonStatus> => unwrap(getApiClient().GET("/daemon/status")),
  port: (): Promise<DaemonPort> => unwrap(getApiClient().GET("/daemon/port")),
  setPort: (port: number): Promise<DaemonPort> =>
    unwrap(getApiClient().PUT("/daemon/port", { body: { port } })),
  residency: (): Promise<DaemonResidency> => unwrap(getApiClient().GET("/daemon/residency")),
  setResidency: (body: DaemonResidencyIn): Promise<DaemonResidency> =>
    unwrap(getApiClient().PUT("/daemon/residency", { body })),
  /** Ask a daemon waiting in its setup state to look for git again. */
  setupCheck: (): Promise<DaemonSetupCheck> => unwrap(getApiClient().POST("/daemon/setup/check")),
  /** The upgrade hand-off and the daemon's release check. */
  upgrade: (): Promise<DaemonUpgrade> => unwrap(getApiClient().GET("/daemon/upgrade")),
  /** Check for a newer release of the installer's binaries now. */
  checkUpgrade: (): Promise<DaemonUpgrade> => unwrap(getApiClient().POST("/daemon/upgrade/check")),
  setUpgradeAutoCheck: (enabled: boolean): Promise<DaemonUpgrade> =>
    unwrap(getApiClient().PUT("/daemon/upgrade/auto-check", { body: { enabled } })),
};
