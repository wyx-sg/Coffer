// e2e/web/specs/shell_settings.spec.ts
//
// Settings as a modal over the current page (change revise-web-ui-ia): six
// tabs grouped by what they manage (General, Security, Data, Daemon, About,
// Features), each at /settings/<tab>; the version menu's language switch; and no shutdown
// control anywhere.

import { expect, test } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { beforeEachInjectToken, readDaemonToken } from "./_helpers";

beforeEachInjectToken();

acceptance(
  "web-ui",
  "settings layout uses the redesigned tabbed sidebar",
  async ({ page }) => {
    // Opened from a page, Settings is a modal over it.
    await page.goto("/mcp-servers");
    await expect(
      page.getByRole("heading", { level: 1, name: "MCP servers" }),
    ).toBeVisible();
    await page.getByTestId("sidebar-settings").click();
    await expect(page).toHaveURL(/\/settings\/general$/);
    const modal = page.getByTestId("settings-modal");
    await expect(modal).toBeVisible();

    // Six tabs, in this order.
    const tabs = modal
      .getByRole("navigation", { name: "Settings sections" })
      .getByRole("link");
    await expect(tabs).toHaveText([
      "General",
      "Security",
      "Data",
      "Daemon",
      "Features",
      "About",
    ]);

    // Clicking a tab swaps the pane without closing the modal.
    await modal.getByRole("link", { name: /^About$/ }).click();
    await expect(page).toHaveURL(/\/settings\/about$/);
    await expect(modal.getByTestId("settings-about-head")).toBeVisible();

    // Escape closes it onto the page underneath, at that page's route.
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(/\/mcp-servers$/);
    await expect(modal).toHaveCount(0);

    // A fresh load of a Settings tab opens it over Overview; closing lands on /.
    await page.goto("/settings/daemon");
    await expect(page.getByTestId("settings-modal")).toBeVisible();
    await expect(page.getByTestId("settings-daemon-status")).toBeVisible();
    await page.getByRole("button", { name: "Close settings" }).click();
    await expect(page).toHaveURL(/\/$/);
  },
);

acceptance(
  "experimental-features",
  "a pinned feature's switch is disabled",
  async ({ page }) => {
    // The e2e daemon pins every experimental feature on (`COFFER_FEATURES`),
    // so the tab lists the two in registry order, each with its Experimental
    // mark, and every switch is disabled with the pin named as the reason.
    await page.goto("/settings/features");
    const pane = page.getByTestId("settings-pane-features");
    for (const [key, name] of [
      ["knowledge", "Knowledge"],
      ["memory", "Memory"],
    ]) {
      const row = pane.getByTestId(`feature-${key}`);
      await expect(row).toContainText("Experimental");
      await expect(row).toContainText(/Pinned by COFFER_FEATURES/);
      const toggle = row.getByRole("switch", { name });
      await expect(toggle).toBeChecked();
      await expect(toggle).toBeDisabled();
    }
    // Sync and model providers graduated: no switch.
    await expect(pane.getByTestId("feature-sync")).toHaveCount(0);
    await expect(pane.getByTestId("feature-models")).toHaveCount(0);
  },
);

acceptance(
  "web-ui",
  "settings offers no shutdown control",
  async ({ page }) => {
    // No Settings tab exposes a daemon-shutdown control — stopping the
    // daemon from the page kills the page. Every tab is visited, and each is
    // first pinned to a card heading it renders itself, so a pane that failed
    // to mount can't satisfy the absence checks vacuously.
    const panes: [string, RegExp][] = [
      ["general", /^Speech-to-text$/], // GeneralSettings -> Speech-to-text
      ["security", /^Encryption$/], // SecuritySettings
      ["data", /^Vault$/], // DataSettings
      ["daemon", /^Startup$/], // DaemonSettings
      ["about", /^About$/], // AboutPage
      ["features", /^Features$/], // ExperimentalFeaturesSettings
    ];
    for (const [tab, heading] of panes) {
      await page.goto(`/settings/${tab}`);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await expect(
        page.getByRole("button", { name: /shut\s*down/i }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: /stop daemon/i }),
      ).toHaveCount(0);
    }

    // The About tab carries no language selector (the version menu and
    // General carry it) and no developer-only resource-kind list.
    await page.goto("/settings/about");
    await expect(
      page.getByTestId("settings-modal").getByRole("combobox"),
    ).toHaveCount(0);
    await expect(page.getByText(/installed resource kinds/i)).toHaveCount(0);
  },
);

acceptance(
  "web-ui",
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

      // Settings auto-save: there is no Save button — the days field persists on
      // blur. Fill the value, then blur and wait for the PATCH to land.
      const saved = page.waitForResponse(
        (r) =>
          r.url().includes("/retention/policies/") &&
          r.request().method() === "PATCH",
        { timeout: 10_000 },
      );
      await daysInput.fill("45");
      await daysInput.blur();
      await saved;

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
  "web-ui",
  "language switcher round-trips correctly",
  async ({ page }) => {
    await page.goto("/mcp-servers");
    // Sidebar starts in English.
    await expect(
      page.getByRole("link", { name: /MCP servers/i }).first(),
    ).toBeVisible();

    // Language lives in Settings › General (the sidebar footer is one Settings row).
    await page.getByTestId("sidebar-settings").click();
    await page
      .getByRole("group", { name: "Language" })
      .getByRole("button", { name: "中文" })
      .click();
    await page.keyboard.press("Escape");

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

// Settings > Data and > Daemon in a real browser; the component tests
// (DataSettings.test.tsx, DaemonSettings.test.tsx) carry the scenarios'
// acceptance markers. The e2e daemon runs under its own throwaway HOME, so
// clearing its cache or pinning its port touches nothing of the user's.

test("the data tab shows four blocks and clears the rebuildable cache after a confirmation", async ({
  page,
}) => {
  await page.goto("/settings/data");
  const modal = page.getByTestId("settings-modal");
  for (const block of ["vault", "local", "history", "cache"]) {
    await expect(modal.getByTestId(`settings-data-${block}`)).toBeVisible();
  }
  await expect(modal.getByText(/this mac only/i)).toHaveCount(0);
  await expect(modal.locator("#forever-mcp_invocations")).toBeVisible();

  await modal
    .getByTestId("settings-data-cache")
    .getByRole("button", { name: /^clear$/i })
    .click();
  const dialog = page.getByRole("dialog", { name: /clear the cache/i });
  await expect(dialog).toBeVisible();
  const cleared = page.waitForResponse(
    (r) =>
      r.url().includes("/storage/cache/clear") &&
      r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: /clear cache/i }).click();
  expect((await cleared).ok()).toBe(true);
  await expect(dialog).toHaveCount(0);
});

test("the daemon tab refuses a port out of range and leaves a saved one pending until restart", async ({
  page,
}) => {
  const { token, port } = readDaemonToken();
  const putPort = (p: number) =>
    fetch(`http://127.0.0.1:${port}/api/v1/daemon/port`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-Coffer-Token": token,
        "X-Coffer-Actor": "e2e",
      },
      body: JSON.stringify({ port: p }),
    });
  try {
    await page.goto("/settings/daemon");
    const modal = page.getByTestId("settings-modal");
    await expect(modal.getByTestId("settings-daemon-status")).toContainText(
      `127.0.0.1:${port}`,
    );
    // A browser offers a Restart control (the daemon restarts itself), never
    // a command to copy.
    await expect(
      modal
        .getByTestId("settings-daemon-status")
        .getByRole("button", { name: /^restart$/i }),
    ).toBeVisible();
    await expect(modal.getByText("coffer daemon restart")).toHaveCount(0);
    await expect(modal.getByText(/token/i)).toHaveCount(0);

    // The field holds the port of the next start (the suite's daemon binds a
    // port from its test range, so that one may differ from the bound port).
    const configured = (await (
      await fetch(`http://127.0.0.1:${port}/api/v1/daemon/port`, {
        headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
      })
    ).json()) as { port: number };
    const field = modal.getByRole("textbox", { name: /^port$/i });
    await expect(field).toHaveValue(String(configured.port));
    // The row has no Save button: Enter applies the value.
    await field.fill("80");
    await field.press("Enter");
    await expect(
      modal.getByRole("alert").getByText(/use a port from 1024 to 65535/i),
    ).toBeVisible();

    const next = port === 65000 ? 65001 : 65000;
    await field.fill(String(next));
    await field.press("Enter");
    await expect(
      modal.getByTestId("settings-daemon-port-pending"),
    ).toContainText(`Port ${next} saved`);
    // Until the restart the status keeps the port it answers on.
    await expect(modal.getByTestId("settings-daemon-status")).toContainText(
      `127.0.0.1:${port}`,
    );
  } finally {
    // Best effort: the suite's HOME is throwaway, and its daemon binds from
    // its test range whatever the file says.
    await putPort(port).catch(() => undefined);
  }
});
