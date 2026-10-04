// e2e/web/specs/shell_activity.spec.ts
//
// The three records Coffer keeps reach a person at /activity: Everything plus
// one tab per record. This file covers the half that needs a real browser and a
// real daemon: an old /audit bookmark resolves here instead of dead-ending and
// the page shows a row the daemon actually wrote; a record written while the
// reader has one open is held behind "N new"; and the search narrows a tab to
// the records the daemon matched.
//
// Per-tab columns, the drawer and a failing tab's error are exercised in
// frontend/src/pages/activity/ActivityPage.test.tsx, where each record's
// payload can be fixed — a browser cannot make the daemon log a chosen line on
// cue, nor take one route away mid-run.

import { expect, test } from "@playwright/test";
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
        /Tool calls/i,
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

test("a record written while one is open waits behind the new pill until it is closed", async ({
  page,
}) => {
  const first = generateUniqueName("e2eheldone");
  const second = generateUniqueName("e2eheldtwo");
  try {
    await registerFakeServer(first);
    await page.goto("/activity?tab=changes");
    const row = page.locator("tr[data-record]", { hasText: first });
    await expect(row.first()).toBeVisible({ timeout: 10_000 });

    // Open the row: it opens as a dialog and the list holds still while it
    // is being read.
    await row.first().click();
    await expect(
      page.getByRole("dialog", { name: new RegExp(first) }),
    ).toBeVisible();

    await registerFakeServer(second);
    // The pill sits behind the modal (out of the accessibility tree), so it is
    // found by its text.
    await expect(page.getByText(/^\d+ new$/)).toBeVisible({ timeout: 15_000 });
    await expect(
      page.locator("tr[data-record]", { hasText: second }),
    ).toHaveCount(0);

    // Closing the record leaves the list live again: what was held goes in.
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.locator("tr[data-record]", { hasText: second }).first(),
    ).toBeVisible();
    await expect(page.getByText(/^\d+ new$/)).toHaveCount(0);
  } finally {
    await deregisterMcpServer(first);
    await deregisterMcpServer(second);
  }
});

test("the search narrows the Changes tab to matching records", async ({
  page,
}) => {
  const kept = generateUniqueName("e2efilterkept");
  const other = generateUniqueName("e2efilterother");
  try {
    await registerFakeServer(kept);
    await registerFakeServer(other);
    await page.goto("/activity?tab=changes");
    await expect(
      page.locator("tr[data-record]", { hasText: other }).first(),
    ).toBeVisible({
      timeout: 10_000,
    });

    await page.getByLabel("Filter changes").fill(kept);
    await expect(
      page.locator("tr[data-record]", { hasText: other }),
    ).toHaveCount(0);
    await expect(
      page.locator("tr[data-record]", { hasText: kept }).first(),
    ).toBeVisible();
  } finally {
    await deregisterMcpServer(kept);
    await deregisterMcpServer(other);
  }
});
