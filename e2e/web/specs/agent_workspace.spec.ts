// e2e/web/specs/agent_workspace.spec.ts
//
// Agent Registry / Skill Manager workspace amendment — the agent detail page as a workspace.
//
// One pragmatic happy path against the real daemon: register a codex agent
// whose config dir is seeded with a config.toml carrying one direct MCP
// entry and one plugin, then walk the detail page's tabs and assert each
// workspace facet renders real (file-derived) data:
//   - MCP servers tab shows the seeded direct entry,
//   - Skills tab shows the "Managed by Coffer" pointer at the Skills page
//     (delivery is decided there, on each skill's enable state + scope).
//
// The seed still carries a `[plugins."…"]` table even though the Plugins tab
// was removed: it keeps the fixture a realistic Codex config, and the MCP
// entry must parse out of a file that has plugin tables in it.
//
// Acceptance coverage for the amendment scenarios lives in the backend
// suites (audit already green), so this spec carries no acceptance marker.

import { test, expect } from "@playwright/test";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";
import * as os from "node:os";
import * as path from "node:path";
import * as fs from "node:fs";

beforeEachInjectToken();

// The config dir must NOT embed the agent name (see shell_agents.spec.ts) —
// pages render the config_dir, and a name inside the path would make
// getByText(name) ambiguous under strict mode.
function mkSeededConfigDir(): string {
  const dir = path.join(os.tmpdir(), `coffer-e2e-ws-cfg-${Date.now()}`);
  fs.mkdirSync(dir, { recursive: true });
  // Codex keeps MCP entries AND plugin state in config.toml. The plugin table
  // is seeded for realism only — nothing surfaces it. The cache dir is absent; the
  // row still renders (with a "cache missing" badge), which is all we assert.
  fs.writeFileSync(
    path.join(dir, "config.toml"),
    [
      "[mcp_servers.e2e-direct]",
      'command = "echo"',
      'args = ["hello"]',
      "",
      "[marketplaces.e2e-market]",
      'source_type = "github"',
      'source = "owner/repo"',
      "",
      '[plugins."e2e-plugin@e2e-market"]',
      "enabled = true",
      "",
    ].join("\n"),
  );
  return dir;
}

async function deleteAgentByApi(name: string): Promise<void> {
  try {
    const { token, port } = readDaemonToken();
    await fetch(`http://127.0.0.1:${port}/api/v1/agents/${name}`, {
      method: "DELETE",
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
    });
  } catch {
    // best-effort
  }
}

test("agent workspace tabs render MCP entries and the Skills-page pointer", async ({
  page,
}) => {
  const { token, port } = readDaemonToken();
  const name = `e2e-ws-${Date.now().toString(36)}`;
  const configDir = mkSeededConfigDir();

  try {
    // Seed the agent via the daemon API (same approach as shell_agents).
    const createResp = await fetch(`http://127.0.0.1:${port}/api/v1/agents`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Coffer-Token": token,
        "X-Coffer-Actor": "e2e",
      },
      body: JSON.stringify({
        type: "codex",
        name,
        config_dir: configDir,
        description: "e2e workspace",
      }),
    });
    expect(createResp.status).toBe(201);

    // Open the agent detail page.
    await page.goto(`/agents/${name}`);
    await expect(page.getByRole("tab", { name: /mcp servers/i })).toBeVisible({
      timeout: 10_000,
    });

    // MCP servers tab — the direct entry parsed from config.toml renders.
    await page.getByRole("tab", { name: /mcp servers/i }).click();
    await expect(page.getByText("e2e-direct", { exact: true })).toBeVisible({
      timeout: 10_000,
    });

    // Skills tab — the tab manages nothing; it points at the Skills page,
    // where a skill's enable state + scope decide who it reaches.
    await page.getByRole("tab", { name: /^skills$/i }).click();
    await expect(
      page.getByRole("button", { name: /open the skills page/i }),
    ).toBeVisible({ timeout: 10_000 });
  } finally {
    await deleteAgentByApi(name);
    try {
      fs.rmSync(configDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }
});
