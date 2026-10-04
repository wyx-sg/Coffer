// e2e/web/specs/shell_memory.spec.ts
//
// The /memory overview against a live daemon: the partitions area renders from
// the real REST answer.
//
// The e2e daemon runs on an isolated HOME, so it normally has no partitions
// and the page shows its first-run welcome in place of the table; a daemon
// whose background read has already produced one shows the table instead. The walk asserts whichever the daemon's
// own partition list says, so it holds either way.
//
// No acceptance marker: the memory scenarios are pinned by the component
// tests, which can assert the page's contents far more precisely. What this
// adds is that the page and the partitions route agree
// against a live daemon.

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

test("the Memory page shows the partitions area", async ({ page }) => {
  const { base, headers } = api();
  const res = await page.request.get(`${base}/memory/partitions`, { headers });
  expect(res.ok()).toBe(true);
  const { partitions } = (await res.json()) as { partitions: unknown[] };

  await page.goto("/memory");
  await expect(
    page.getByRole("heading", { name: "Memory", level: 1 }),
  ).toBeVisible();

  if (partitions.length === 0) {
    // First run (canvas 5.2.08 / 5.2.09): the welcome stands in for the
    // table, with the one Update memory action in it, not in the header too.
    await expect(
      page.getByText(/Nothing distilled yet|No agent memory to read/),
    ).toBeVisible();
    await expect(page.getByTestId("memory-partitions")).toHaveCount(0);
    await expect(page.getByRole("table")).toHaveCount(0);
    return;
  }

  const area = page.getByTestId("memory-partitions");
  await expect(area).toBeVisible();
  await expect(area.getByRole("table")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /update memory/i }),
  ).toHaveCount(1);
});
