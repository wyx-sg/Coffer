// e2e/web/specs/shell_activity.spec.ts
//
// UI Shell §User Story 3 — the three records Coffer keeps reach a person at
// /activity, one tab and one table each. This file covers the half that needs a
// real browser and a real daemon: an old /audit bookmark resolves here instead
// of dead-ending, the page it lands on renders all three tabs, and the Changes
// tab picks up a row the daemon actually wrote.
//
// Per-tab columns, the row expand and a failing tab's error are exercised in
// frontend/src/pages/activity/ActivityPage.test.tsx, where each record's
// payload can be fixed — a browser cannot make the daemon log a chosen line on
// cue, nor take one route away mid-run.

import { expect } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { acceptance } from "./_acceptance";
import {
  beforeEachInjectToken,
  deregisterMcpServer,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const FAKE_SERVER = path.join(
  REPO_ROOT,
  "backend/tests/fixtures/fake_mcp_server.py",
);

beforeEachInjectToken();

// Registering a server writes an audit row — the one lane a browser can put a
// known line into.
async function registerFakeServer(name: string): Promise<void> {
  const { token, port } = readDaemonToken();
  const r = await fetch(`http://127.0.0.1:${port}/api/v1/resources`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: JSON.stringify({
      kind: "mcp_server",
      name,
      config: {
        transport: {
          type: "stdio",
          command: PYTHON,
          args: [FAKE_SERVER, "--scenario", "basic", "--tools", "read_file"],
        },
      },
    }),
  });
  if (!r.ok) throw new Error(`register failed: ${r.status} ${await r.text()}`);
}

acceptance("web-ui", "legacy /audit redirects to activity", async ({ page }) => {
  const name = generateUniqueName("e2eactivity");
  try {
    await registerFakeServer(name);

    // The old bookmark, not /activity — the redirect is what is under test.
    await page.goto("/audit");
    await expect(page).toHaveURL(/\/activity$/);

    await expect(
      page.getByRole("heading", { name: /^Activity$/ }),
    ).toBeVisible();
    // One tab per record — the page's whole shape.
    for (const tab of [/Changes/i, /MCP calls/i, /Daemon/i]) {
      await expect(page.getByRole("tab", { name: tab })).toBeVisible();
    }

    // Changes is the landing tab, and it picks the registration up as a
    // plain-language line naming the server, not a raw `resource_registered`.
    await expect(page.getByText(new RegExp(name))).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/resource_registered/)).toHaveCount(0);
  } finally {
    await deregisterMcpServer(name);
  }
});
