// e2e/web/specs/_helpers.ts
//
// Shared utilities for the e2e acceptance suite.
// Node 18+ fetch API is used for direct API calls; Playwright's `page`
// object is used for browser interactions.

import { test } from "@playwright/test";
import * as fs from "node:fs";

export interface DaemonInfo {
  token: string;
  port: number;
}

/**
 * Read the daemon's token and port from the sentinel file written by
 * start_daemon.sh.  The daemon writes ~/.coffer/daemon.json; in the e2e
 * suite HOME is overridden by the script and the chosen path is persisted
 * to /tmp/coffer-e2e-home.path so we can find it here.
 */
export function readDaemonToken(): DaemonInfo {
  const homePath = fs.readFileSync("/tmp/coffer-e2e-home.path", "utf-8").trim();
  const json = fs.readFileSync(`${homePath}/.coffer/daemon.json`, "utf-8");
  const parsed = JSON.parse(json) as { token: string; port: number };
  return { token: parsed.token, port: parsed.port };
}

/**
 * Register a `test.beforeEach` that injects the daemon token into
 * localStorage before every navigation.  Must be called at the top level
 * of each spec file (not inside a describe block).
 */
export function beforeEachInjectToken(): void {
  test.beforeEach(async ({ context }) => {
    const { token } = readDaemonToken();
    await context.addInitScript((tok: string) => {
      window.localStorage.setItem("coffer.token", tok);
    }, token);
  });
}

/**
 * Generate a unique server name for a test run so parallel or repeated
 * runs don't collide with each other in the shared daemon DB.
 */
export function generateUniqueName(prefix: string): string {
  return `${prefix}${Date.now().toString(36)}`;
}

/**
 * Best-effort cleanup helper — deregister an mcp_server resource the test
 * registered. Without this, leaked servers accumulate across tests; the
 * next aggregate `tools/list` then tries to respawn each one (the gateway
 * caps each at 5s but ~5 dead leftovers still hit ~25s total, easily
 * timing out clients). Failures here are swallowed so cleanup never
 * masks the real test failure.
 */
export async function deregisterMcpServer(name: string): Promise<void> {
  try {
    const { token, port } = readDaemonToken();
    await fetch(
      `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${name}`,
      {
        method: "DELETE",
        headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
      },
    );
  } catch {
    // best-effort
  }
}
