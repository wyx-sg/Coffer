// e2e/web/specs/shell_overview.spec.ts
//
// The Overview at `/` against a real daemon: a stdio MCP server whose launcher
// does not exist on this machine is something that needs the person, so the
// daemon's attention list reports it (mcp_missing_launcher) and the page's
// "Needs you" section lists it with the daemon's reason and one action that
// opens the server's page.
//
// Ordering, the calm card, first run, a failing tile and live refresh are
// covered in frontend/src/pages/OverviewPage.test.tsx, where the attention
// payload can be fixed.

import { expect, test } from "@playwright/test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  beforeEachInjectToken,
  deregisterMcpServer,
  generateUniqueName,
  readDaemonToken,
  resolveResourceUid,
} from "./_helpers";

beforeEachInjectToken();

const MISSING_LAUNCHER = "coffer-e2e-missing-launcher-xyz";

function headers(): Record<string, string> {
  const { token } = readDaemonToken();
  return {
    "Content-Type": "application/json",
    "X-Coffer-Token": token,
    "X-Coffer-Actor": "e2e",
  };
}

function api(route: string): string {
  const { port } = readDaemonToken();
  return `http://127.0.0.1:${port}/api/v1${route}`;
}

async function registerServerWithMissingLauncher(name: string): Promise<void> {
  const r = await fetch(api("/resources"), {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      kind: "mcp_server",
      name,
      config: {
        transport: { type: "stdio", command: MISSING_LAUNCHER, args: [] },
      },
    }),
  });
  if (!r.ok) throw new Error(`register failed: ${r.status} ${await r.text()}`);
}

/**
 * With no agent registered the Overview shows its first-run panel instead of
 * "Needs you", so make sure one exists. Returns the uid of the agent this test
 * registered (to remove afterwards), or null when one was already there.
 */
async function ensureAnAgent(configDir: string): Promise<string | null> {
  const list = await fetch(api("/agents"), { headers: headers() });
  const body = (await list.json()) as { items: unknown[] };
  if (body.items.length > 0) return null;
  const r = await fetch(api("/agents"), {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ type: "claude_code", config_dir: configDir }),
  });
  if (!r.ok)
    throw new Error(`agent register failed: ${r.status} ${await r.text()}`);
  return ((await r.json()) as { uid: string }).uid;
}

test("overview lists an MCP server whose launcher is missing, with its reason and action", async ({
  page,
}) => {
  const name = generateUniqueName("e2eoverview");
  const configDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "coffer-e2e-overview-cfg-"),
  );
  let agentUid: string | null = null;
  try {
    agentUid = await ensureAnAgent(configDir);
    await registerServerWithMissingLauncher(name);
    const uid = await resolveResourceUid("mcp_server", name);
    expect(uid).not.toBeNull();

    await page.goto("/");
    await expect(
      page.getByRole("heading", { level: 1, name: "Overview" }),
    ).toBeVisible();

    const needsYou = page.getByRole("region", { name: "Needs you" });
    const row = needsYou.getByRole("listitem").filter({ hasText: name });
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row).toContainText(
      `Its launcher \`${MISSING_LAUNCHER}\` is not installed`,
    );
    await expect(row.getByRole("img", { name: "Failing" })).toBeVisible();

    const action = row.getByRole("link", {
      name: new RegExp(`^Test again: ${name}$`),
    });
    await expect(action).toHaveAttribute("href", `/mcp-servers/${uid}`);
    await action.click();
    // The uid address redirects to the server's name-keyed page.
    await expect(page).toHaveURL(new RegExp(`/mcp-servers/${name}$`), {
      timeout: 10_000,
    });
  } finally {
    await deregisterMcpServer(name);
    if (agentUid) {
      await fetch(api(`/agents/${agentUid}`), {
        method: "DELETE",
        headers: headers(),
      }).catch(() => undefined);
    }
    fs.rmSync(configDir, { recursive: true, force: true });
  }
});
