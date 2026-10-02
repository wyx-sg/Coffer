// e2e/web/specs/shell_usage.spec.ts
//
// The Usage page at /usage against a real, fresh daemon. Nothing has gone
// through the local model proxy and no agent session has reported quota, so
// the page shows its first-run state (canvas 6.4.03): the API-key section is
// only its empty state — no range, filters or export to narrow nothing — and
// links to Model providers, and Claude Code's quota row says no reading has
// been seen yet and waits. A range in the address still loads the same state.
//
// The range, the Agent and Provider filters, the custom range's note, Export
// CSV, tiles, the chart, the breakdown table, quota meters and their tones are
// covered in frontend/src/pages/UsagePage.test.tsx, where the summary and the
// quota windows can be fixed — a browser cannot make the proxy meter a request
// on cue. The CSV route itself is covered by the backend's route tests.

import { expect, test } from "@playwright/test";
import { beforeEachInjectToken } from "./_helpers";

beforeEachInjectToken();

test("a fresh daemon shows the first-run state without controls", async ({
  page,
}) => {
  await page.goto("/usage");
  await expect(page.getByRole("heading", { name: /^Usage$/ })).toBeVisible();

  const usage = page.getByRole("region", { name: "API-key providers" });
  await expect(usage.getByText("No API-key usage yet")).toBeVisible();
  await expect(
    usage.getByRole("link", { name: "Open Model providers" }),
  ).toHaveAttribute("href", "/model-providers");
  await expect(usage.getByRole("group", { name: "Period" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "More actions" })).toHaveCount(
    0,
  );

  const quota = page.getByRole("region", { name: "Subscription quota" });
  await expect(quota.getByText("No quota reading yet").first()).toBeVisible();
  await expect(
    quota.getByText("Appears after your next Claude Code response."),
  ).toBeVisible();
  // The statusline wrapper is handed to an agent (Principle IV), never
  // switched on from the page and never shown as a command to run.
  await expect(quota.getByText(/point Claude Code's status line at/)).toBeVisible();
  await expect(quota.getByRole("button", { name: "Copy prompt" })).toBeVisible();
  await expect(quota.getByRole("button", { name: "Ask an agent" })).toBeVisible();
  await expect(quota.getByText(/coffer usage statusline --/)).toHaveCount(0);
  await expect(page.getByRole("switch")).toHaveCount(0);
});

test("a range in the address still shows the first-run state", async ({
  page,
}) => {
  await page.goto("/usage?range=30d");
  const usage = page.getByRole("region", { name: "API-key providers" });
  await expect(usage.getByText("No API-key usage yet")).toBeVisible();
  await expect(page).toHaveURL(/\/usage\?range=30d$/);
});
