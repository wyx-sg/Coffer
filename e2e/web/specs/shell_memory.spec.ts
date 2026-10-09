// e2e/web/specs/shell_memory.spec.ts
//
// The /memory sync page against a live daemon: it renders from the real
// GET /memory/sync/state answer.
//
// The e2e daemon runs on an isolated HOME, so it normally has no agent with
// memory to sync and the page shows its "No agent to sync" state; a daemon
// with an agent registered shows the projects and agents sections with one
// Sync now. The walk asserts whichever the daemon's own sync state says, so it
// holds either way.
//
// No acceptance marker: the memory scenarios are pinned by the component
// tests, which can assert the page's contents far more precisely. What this
// adds is that the page and the sync-state route agree against a live daemon.

import { expect, test } from "@playwright/test";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

function api() {
  const { token, port } = readDaemonToken();
  return {
    base: `http://127.0.0.1:${port}/api/v1`,
    headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
  };
}

test("the Memory page shows the sync state", async ({ page }) => {
  const { base, headers } = api();
  const res = await page.request.get(`${base}/memory/sync/state`, { headers });
  expect(res.ok()).toBe(true);
  const { agents } = (await res.json()) as { agents: unknown[] };

  await page.goto("/memory");
  await expect(
    page.getByRole("heading", { name: "Memory", level: 1 }),
  ).toBeVisible();
  // Nothing on the page edits a memory's text.
  await expect(page.getByRole("textbox", { name: /memory/i })).toHaveCount(0);

  if (agents.length === 0) {
    await expect(page.getByText("No agent to sync")).toBeVisible();
    await expect(page.getByTestId("memory-projects")).toHaveCount(0);
    return;
  }

  await expect(page.getByTestId("memory-projects")).toBeVisible();
  await expect(page.getByTestId("memory-agents")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^(Sync now|Syncing…)$/ }),
  ).toHaveCount(1);
});
