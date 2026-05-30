// e2e/web/specs/shell_settings.spec.ts
//
// Spec 002 §User Story 5 — the redesigned Settings: tabs grouped by what
// the user manages (Data / About; the desktop app adds App), the daemon
// never surfaced as a concept, the sidebar language switcher, and the
// removal of the confusing controls.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

acceptance(
  "002-ui-shell",
  "settings layout uses the redesigned tabbed sidebar",
  async ({ page }) => {
    await page.goto("/settings");
    // /settings index redirects to the first tab — General.
    await expect(page).toHaveURL(/\/settings\/general/);

    // The browser shows General, Data, and About (the App tab is
    // desktop-only). The daemon is never a tab.
    await expect(page.getByRole("link", { name: /^General$/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Data$/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^About$/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Daemon$/ })).toHaveCount(0);

    // Click About — content swaps without leaving /settings/*
    await page.getByRole("link", { name: /^About$/ }).click();
    await expect(page).toHaveURL(/\/settings\/about/);
    // Assert the About pane's own heading is now rendered — proves the
    // outlet actually swapped, not just the URL. Without this, a regression
    // where the link updates the URL but the inner pane fails to mount
    // would still pass.
    await expect(
      page.getByRole("heading", { name: /about coffer/i }),
    ).toBeVisible();
  },
);

acceptance(
  "002-ui-shell",
  "settings drops the confusing controls",
  async ({ page }) => {
    // No Settings tab exposes a daemon-shutdown or token-rotation control
    // — both are rare/dangerous actions that belong on the CLI.
    for (const tab of ["data", "about"]) {
      await page.goto(`/settings/${tab}`);
      await expect(
        page.getByRole("button", { name: /shut\s*down/i }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: /rotate token/i }),
      ).toHaveCount(0);
    }

    // The daemon is never surfaced — no Daemon tab, no status panel.
    await expect(page.getByRole("link", { name: /^Daemon$/ })).toHaveCount(0);

    // The About tab carries no language selector (the sidebar switcher is
    // the single source) and no developer-only resource-kind list.
    await page.goto("/settings/about");
    await expect(page.locator("main").getByRole("combobox")).toHaveCount(0);
    await expect(page.getByText(/installed resource kinds/i)).toHaveCount(0);
  },
);

acceptance(
  "002-ui-shell",
  "retention period persists across reload",
  async ({ page }) => {
    const { token, port } = readDaemonToken();

    // Helper to restore keep-forever state (retention_days: null) no matter
    // what happens during the test body.
    const restoreRetention = () =>
      fetch(
        `http://127.0.0.1:${port}/api/v1/retention/policies/mcp_invocations`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "X-Coffer-Token": token,
            "X-Coffer-Actor": "e2e",
          },
          body: JSON.stringify({ retention_days: null }),
        },
      );

    try {
      // Navigate to data settings
      await page.goto("/settings/data");

      // Locate the mcp_invocations policy row (the switch id is forever-mcp_invocations)
      const foreverSwitch = page.locator("#forever-mcp_invocations");
      await expect(foreverSwitch).toBeVisible({ timeout: 10_000 });

      // If "Keep forever" is on, turn it off so the days field appears
      const isChecked = await foreverSwitch.isChecked();
      if (isChecked) {
        await foreverSwitch.click();
      }

      // Wait for the days input to appear and set a distinctive value
      const daysInput = page.locator("#days-mcp_invocations");
      await expect(daysInput).toBeVisible({ timeout: 5_000 });
      await daysInput.fill("45");

      // Click Save — the Save button is a sibling of the days input inside the
      // same flex container. Navigate up to the closest ancestor that contains
      // the days input but NOT the audit_log days input, then pick its Save.
      // The most reliable way is to use the label-to-input association: the input
      // has id=days-mcp_invocations, so its label is "Retention (days)" next to
      // it. We just grab the Save button that's adjacent to that specific input
      // by going via the innermost wrapping div.
      // The Save button is a sibling of the days-row flex container; both live
      // inside a parent flex container. Use that parent to scope the search.
      const saveBtnContainer = page.locator("div.flex.shrink-0").filter({
        has: page.locator("#days-mcp_invocations"),
      });
      const saveBtn = saveBtnContainer.getByRole("button", { name: /save/i });
      await saveBtn.click();

      // Wait for dirty-flag to clear (button becomes disabled again after save)
      await expect(saveBtn).toBeDisabled({ timeout: 5_000 });

      // Reload and confirm the value persisted
      await page.reload();
      const daysInputAfter = page.locator("#days-mcp_invocations");
      await expect(daysInputAfter).toBeVisible({ timeout: 10_000 });
      await expect(daysInputAfter).toHaveValue("45");
    } finally {
      // Always restore keep-forever so later tests start with a clean slate,
      // even if an assertion above fails mid-test.
      await restoreRetention();
    }
  },
);

acceptance(
  "002-ui-shell",
  "language switcher round-trips correctly",
  async ({ page }) => {
    await page.goto("/resources");
    // Sidebar starts in English.
    await expect(
      page.getByRole("link", { name: /MCP servers/i }).first(),
    ).toBeVisible();

    // The sidebar language switcher is a button group (EN / 中).
    await page.getByRole("button", { name: "中" }).click();

    // Sidebar labels switch to Chinese within the same frame.
    await expect(
      page.getByRole("link", { name: /MCP 服务器/ }).first(),
    ).toBeVisible();

    // The preference persists across a reload.
    await page.reload();
    await expect(
      page.getByRole("link", { name: /MCP 服务器/ }).first(),
    ).toBeVisible();
  },
);
