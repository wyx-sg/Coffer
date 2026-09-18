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
 * Register a `test.beforeEach` that puts the daemon token on the page's
 * `window.__COFFER_TOKEN__` before every navigation.  Must be called at the
 * top level of each spec file (not inside a describe block).
 *
 * A page the daemon serves already carries this global — the daemon injects it
 * into its index.html — so this is belt-and-braces for specs that navigate
 * somewhere else first. It is the same global either way; nothing is stored.
 */
export function beforeEachInjectToken(): void {
  test.beforeEach(async ({ context }) => {
    const { token } = readDaemonToken();
    await context.addInitScript((tok: string) => {
      (window as unknown as { __COFFER_TOKEN__?: string }).__COFFER_TOKEN__ = tok;
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
    // The route addresses the uid; the test knows the name it registered.
    const uid = await resolveResourceUid("mcp_server", name);
    if (uid === null) return; // already gone — best-effort cleanup
    await fetch(
      `http://127.0.0.1:${port}/api/v1/resources/${uid}`,
      {
        method: "DELETE",
        headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
      },
    );
  } catch {
    // best-effort
  }
}

/**
 * Resolve a resource NAME to the uid every route now addresses it by.
 *
 * A resource's identity is an opaque uid (ADR
 * resource-identity-is-an-immutable-uid); a test knows the name it registered,
 * so it looks the uid up the same way the CLI does — through the one route
 * allowed to find a resource by its label. Returns null when nothing matches,
 * so a cleanup path can stay best-effort.
 */
export async function resolveResourceUid(
  kind: string,
  name: string,
): Promise<string | null> {
  const { token, port } = readDaemonToken();
  const resp = await fetch(
    `http://127.0.0.1:${port}/api/v1/resources?kind=${encodeURIComponent(kind)}` +
      `&name=${encodeURIComponent(name)}`,
    { headers: { "X-Coffer-Token": token } },
  );
  if (!resp.ok) return null;
  const body = (await resp.json()) as { resources: Array<{ uid: string }> };
  return body.resources[0]?.uid ?? null;
}
