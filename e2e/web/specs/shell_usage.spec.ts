// e2e/web/specs/shell_usage.spec.ts
//
// Model providers › Usage at /model-providers?tab=usage against a real, fresh
// daemon. Nothing has gone through the local model proxy, so the tab shows its
// first-run state (Agents canvas 2.2.22): a whole-page empty state with "Open
// Providers", and no time range, filters or export to narrow nothing. A range
// in the address still loads the same state, and /usage is no longer a page.
//
// The range, the Agent and Provider filters, Export CSV, tiles, the chart and
// the breakdown table are covered in
// frontend/src/components/usage/UsageTab.test.tsx, where the summary can be
// fixed — a browser cannot make the proxy meter a request on cue. The CSV route
// itself is covered by the backend's route tests.

import { expect, test } from "@playwright/test";
import { beforeEachInjectToken } from "./_helpers";

beforeEachInjectToken();

test("a fresh daemon shows the first-run state without controls", async ({
  page,
}) => {
  await page.goto("/model-providers?tab=usage");
  await expect(
    page.getByRole("heading", { name: /^Model providers$/ }),
  ).toBeVisible();
  await expect(page.getByRole("tab", { name: "Usage" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await expect(page.getByText("No API-key usage yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Export CSV" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Last 7 days/ })).toHaveCount(
    0,
  );

  // "Open Providers" is the other tab, not a navigation away.
  await page.getByRole("button", { name: "Open Providers" }).click();
  await expect(page).toHaveURL(/\/model-providers$/);
  await expect(page.getByRole("tab", { name: "Providers" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("a range in the address still shows the first-run state", async ({
  page,
}) => {
  await page.goto("/model-providers?tab=usage&range=30d");
  await expect(page.getByText("No API-key usage yet")).toBeVisible();
});

test("/usage is not a page any more", async ({ page }) => {
  await page.goto("/usage");
  await expect(page.getByText("Nothing lives at this address")).toBeVisible();
});
