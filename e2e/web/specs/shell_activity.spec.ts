// e2e/web/specs/shell_activity.spec.ts
//
// The three records Coffer keeps reach a person at /activity: Everything plus
// one tab per record. This file covers the half that needs a real browser and a
// real daemon: an old /audit bookmark resolves here instead of dead-ending and
// the page shows a row the daemon actually wrote; a record written while the
// reader has one open is held behind "N new"; and the ⋯ menu's export writes
// exactly the filtered records to a file.
//
// Per-tab columns, the drawer and a failing tab's error are exercised in
// frontend/src/pages/activity/ActivityPage.test.tsx, where each record's
// payload can be fixed — a browser cannot make the daemon log a chosen line on
// cue, nor take one route away mid-run.

import { expect, test } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
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

test(
  "activity opens on Everything with one tab per record",
  async ({ page }) => {
    const name = generateUniqueName("e2eactivity");
    try {
      await registerFakeServer(name);

      await page.goto("/activity");

      await expect(
        page.getByRole("heading", { name: /^Activity$/ }),
      ).toBeVisible();
      // Everything, then one tab per record — the page's whole shape.
      for (const tab of [
        /Everything/i,
        /Changes/i,
        /MCP calls/i,
        /Daemon log/i,
      ]) {
        await expect(page.getByRole("tab", { name: tab })).toBeVisible();
      }

      // Everything is the landing tab, and it picks the registration up as a
      // plain-language line naming the server, not a raw `resource_registered`.
      await expect(page.getByText(new RegExp(name)).first()).toBeVisible({
        timeout: 10_000,
      });
      await expect(page.getByText(/resource_registered/)).toHaveCount(0);
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

// revise-web-ui-ia: web-ui "new records are held while the user reads" — the
// marker is added when the change is archived.
test("a record written while one is open waits behind the new pill", async ({
  page,
}) => {
  const first = generateUniqueName("e2eheldone");
  const second = generateUniqueName("e2eheldtwo");
  try {
    await registerFakeServer(first);
    await page.goto("/activity?tab=changes");
    const row = page.locator("tr[data-record]", { hasText: first });
    await expect(row.first()).toBeVisible({ timeout: 10_000 });

    // Open the row: the list holds still while it is being read.
    await row.first().click();
    await expect(
      page.getByRole("complementary", { name: "Details" }),
    ).toBeVisible();

    await registerFakeServer(second);
    const pill = page.getByRole("button", { name: /^\d+ new$/ });
    await expect(pill).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator("tr[data-record]", { hasText: second }),
    ).toHaveCount(0);

    await pill.click();
    await expect(
      page.locator("tr[data-record]", { hasText: second }).first(),
    ).toBeVisible();
  } finally {
    await deregisterMcpServer(first);
    await deregisterMcpServer(second);
  }
});

// revise-web-ui-ia: web-ui "export from the menu honours the filters".
test("export from the menu writes only the filtered records", async ({
  page,
}) => {
  const kept = generateUniqueName("e2eexportkept");
  const other = generateUniqueName("e2eexportother");
  try {
    await registerFakeServer(kept);
    await registerFakeServer(other);
    await page.goto("/activity?tab=changes");
    await expect(
      page.locator("tr[data-record]", { hasText: other }).first(),
    ).toBeVisible({
      timeout: 10_000,
    });

    await page.getByLabel("Filter records").fill(kept);
    await expect(
      page.locator("tr[data-record]", { hasText: other }),
    ).toHaveCount(0);

    // The header has no export button; the ⋯ menu carries it.
    await expect(page.getByRole("button", { name: /export/i })).toHaveCount(0);
    await page.getByRole("button", { name: "More" }).click();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("menuitem", { name: "Export as CSV" }).click(),
    ]);
    const file = await download.path();
    const csv = fs.readFileSync(file, "utf-8");
    const rows = csv.trim().split(/\r?\n/).slice(1);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((r) => r.includes(kept))).toBe(true);
    expect(csv).not.toContain(other);
  } finally {
    await deregisterMcpServer(kept);
    await deregisterMcpServer(other);
  }
});
