// e2e/web/specs/shell_memory.spec.ts
//
// The /memory page against a live daemon: it renders from the real GET /memory
// answer.
//
// The e2e daemon runs on an isolated HOME, so it normally holds no memories
// and the page shows its "No memories yet" state; a daemon whose hub holds a
// project shows the projects beside the open project's topic files. The walk
// asserts whichever the daemon's own answer says, so it holds either way.
//
// No acceptance marker: the memory scenarios are pinned by the component
// tests, which can assert the page's contents far more precisely. What this
// adds is that the page and the route agree against a live daemon.

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

test("the Memory page shows the hub", async ({ page }) => {
  const { base, headers } = api();
  const res = await page.request.get(`${base}/memory`, { headers });
  expect(res.ok()).toBe(true);
  const { projects, folder_path } = (await res.json()) as {
    projects: unknown[];
    folder_path: string;
  };

  await page.goto("/memory");
  await expect(
    page.getByRole("heading", { name: "Memory", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText(`Kept in ${folder_path}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Tidy" })).toBeVisible();
  if (projects.length === 0) {
    await expect(page.getByText("No memories yet")).toBeVisible();
  } else {
    await expect(page.getByTestId("memory-list")).toBeVisible();
  }
});
