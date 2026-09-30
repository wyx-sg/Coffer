// e2e/web/specs/shell_usage.spec.ts
//
// The Usage page at /usage against a real, fresh daemon. Nothing has gone
// through the local model proxy and no agent session has reported quota, so
// the page shows its first-run state: the API-key section explains how usage
// starts and links to Model providers, and Claude Code's quota row says no
// reading has been seen yet. The period control writes the range into the URL,
// the custom range says how far back per-request detail is kept, and the ⋯
// menu's Export CSV hands the browser a file with the summary's header row.
//
// Tiles, the chart, the breakdown table, quota meters and their tones are
// covered in frontend/src/pages/UsagePage.test.tsx, where the summary and the
// quota windows can be fixed — a browser cannot make the proxy meter a request
// on cue.

import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

/** Set the MCP-calls window — the one per-request usage detail follows — and
 *  return what it was. Another spec may have left it at "keep forever", which
 *  (rightly) hides the note this spec reads. */
async function setDetailDays(days: number | null): Promise<number | null> {
  const { token, port } = readDaemonToken();
  const url = `http://127.0.0.1:${port}/api/v1/retention/policies`;
  const headers = {
    "Content-Type": "application/json",
    "X-Coffer-Token": token,
  };
  const list = (await (await fetch(url, { headers })).json()) as {
    policies: { table_name: string; retention_days: number | null }[];
  };
  const prior =
    list.policies.find((p) => p.table_name === "mcp_invocations")
      ?.retention_days ?? null;
  const r = await fetch(`${url}/mcp_invocations`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ retention_days: days }),
  });
  if (!r.ok) throw new Error(`retention patch failed: ${r.status}`);
  return prior;
}

test("a fresh daemon shows the first-run state, and the range lives in the URL", async ({
  page,
}) => {
  await page.goto("/usage");
  await expect(page.getByRole("heading", { name: /^Usage$/ })).toBeVisible();

  const usage = page.getByRole("region", { name: "API-key providers" });
  await expect(usage.getByText("No API-key usage yet")).toBeVisible();
  await expect(
    usage.getByRole("link", { name: "Open Model providers" }),
  ).toHaveAttribute("href", "/model-providers");

  const quota = page.getByRole("region", { name: "Subscription quota" });
  await expect(quota.getByText("No quota reading yet").first()).toBeVisible();
  await expect(
    quota.getByText("Appears after your next Claude Code response."),
  ).toBeVisible();
  // The statusline wrapper is described, never switched on from the page.
  await expect(quota.getByText(/coffer usage statusline --/)).toBeVisible();
  await expect(page.getByRole("switch")).toHaveCount(0);

  // 7 days is the default and is not spelled out; another range is.
  const period = usage.getByRole("group", { name: "Period" });
  await expect(period.getByRole("button", { name: "7 days" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await period.getByRole("button", { name: "30 days" }).click();
  await expect(page).toHaveURL(/\/usage\?range=30d$/);
  await expect(period.getByRole("button", { name: "30 days" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.reload();
  await expect(
    page
      .getByRole("region", { name: "API-key providers" })
      .getByRole("button", { name: "30 days" }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("the custom range says how far back per-request detail is kept", async ({
  page,
}) => {
  const prior = await setDetailDays(30);
  try {
    await checkCustomRangeNote(page);
  } finally {
    await setDetailDays(prior);
  }
});

async function checkCustomRangeNote(page: Page): Promise<void> {
  await page.goto("/usage");
  const usage = page.getByRole("region", { name: "API-key providers" });
  await usage.getByRole("button", { name: "Custom…" }).click();
  const dialog = page.getByRole("dialog", { name: "Custom range" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByText(/^Before .+, only daily totals are kept\.$/),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page).toHaveURL(/\/usage$/);
}

test("Export CSV downloads the summary for the current range", async ({
  page,
}) => {
  await page.goto("/usage?range=today");
  await expect(
    page
      .getByRole("region", { name: "API-key providers" })
      .getByText("No API-key usage yet"),
  ).toBeVisible();
  await page.getByRole("button", { name: "More actions" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("menuitem", { name: "Export CSV" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("coffer-usage-today-model.csv");
  const csv = fs.readFileSync(await download.path(), "utf-8");
  // A header row even with nothing in the range.
  expect(csv.trim().split(/\r?\n/).length).toBeGreaterThanOrEqual(1);
  expect(csv.split(/\r?\n/)[0]).toMatch(/requests/i);
});
