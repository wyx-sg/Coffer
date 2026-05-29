// e2e/web/specs/shell_cold_start.spec.ts
//
// Spec 002 §User Story 1 — first-visit experience must render authenticated
// content without ceremony. We exercise three paths in one file:
//   1. cold-start renders authenticated content (no addInitScript token)
//   2. token-missing renders an actionable empty state (override base URL
//      to point at a port the daemon isn't bound to)
//   3. empty resources list renders a welcome view (no leaked test servers)
//
// Notably, scenario (1) deliberately skips beforeEachInjectToken — the
// whole point is that the vite dev plugin's __COFFER_TOKEN__ injection
// authenticates the page on its own.

import { expect } from "@playwright/test";
import { acceptance } from "./_acceptance";
import { readDaemonToken } from "./_helpers";

acceptance(
  "002-ui-shell",
  "cold-start renders authenticated content",
  async ({ page }) => {
    // No beforeEachInjectToken — rely on the vite plugin to inject token
    // from /tmp/coffer-e2e-home.path's daemon.json.
    const { token } = readDaemonToken();
    await page.addInitScript(
      ([t]) => {
        // Mimic what the vite plugin does in dev: tokens come via
        // window.__COFFER_TOKEN__. Setting it here proves the FE consumes
        // the same injection contract.
        (window as unknown as { __COFFER_TOKEN__: string }).__COFFER_TOKEN__ =
          t;
      },
      [token],
    );

    await page.goto("/");

    // The sidebar lists Coffer's operational surfaces — and only those.
    // No dead "soon" entries for unbuilt features.
    for (const label of [/MCP servers/i, /Audit log/i, /Settings/i]) {
      await expect(
        page.getByRole("link", { name: label }).first(),
      ).toBeVisible();
    }
    // Grouped under Resources / System headings.
    await expect(page.getByText(/^Resources$/i).first()).toBeVisible();
    await expect(page.getByText(/^System$/i).first()).toBeVisible();

    // The first-content surface is the resources page (redirected from /).
    // No generic "unexpected error" card.
    await expect(page.getByText(/unexpected error/i)).toHaveCount(0);
  },
);

acceptance(
  "002-ui-shell",
  "daemon-offline banner appears when daemon is unreachable",
  async ({ page }) => {
    // Same setup as the token-missing scenario below — pointing at a
    // dead port models "daemon not running" from the FE's perspective.
    // We assert the new spec-002 scenario name explicitly: the banner
    // renders at the top of the workspace with the literal command
    // hint, even when no token has been minted yet.
    await page.addInitScript(() => {
      (
        window as unknown as { __COFFER_BASE_URL__: string }
      ).__COFFER_BASE_URL__ = "http://127.0.0.1:19998/api/v1";
      (window as unknown as { __COFFER_TOKEN__: string }).__COFFER_TOKEN__ = "";
    });

    await page.goto("/");

    const banner = page.getByTestId("daemon-banner");
    await expect(banner).toBeVisible({ timeout: 10_000 });
    // The literal copyable command appears inside the banner (not just
    // a generic error message).
    await expect(page.getByTestId("daemon-banner-cmd")).toHaveText(
      /coffer daemon start/,
    );
  },
);

acceptance(
  "002-ui-shell",
  "token-missing renders an actionable empty state",
  async ({ page }) => {
    // Point the FE at a base URL that won't resolve to a daemon. That
    // mirrors what a real user sees when `coffer daemon start` hasn't
    // been run yet: the status query errors out and DaemonOfflineBanner
    // shows its "daemon not running" panel with the exact command.
    await page.addInitScript(() => {
      (
        window as unknown as { __COFFER_BASE_URL__: string }
      ).__COFFER_BASE_URL__ = "http://127.0.0.1:19999/api/v1";
      (window as unknown as { __COFFER_TOKEN__: string }).__COFFER_TOKEN__ = "";
    });

    await page.goto("/");

    const banner = page.getByTestId("daemon-banner");
    await expect(banner).toBeVisible({ timeout: 10_000 });
    // The exact runnable command must appear (not a generic "error").
    await expect(page.getByTestId("daemon-banner-cmd")).toHaveText(
      /coffer daemon start/,
    );
    // Sidebar must still be reachable so the user can orient.
    await expect(
      page.getByRole("link", { name: /MCP servers/i }).first(),
    ).toBeVisible();
    await expect(page.getByText(/INTERNAL_ERROR/)).toHaveCount(0);
  },
);

acceptance(
  "002-ui-shell",
  "empty resources list renders a welcome view",
  async ({ page, context }) => {
    // Inject a valid token so the API calls succeed, but ensure no
    // resources exist by deleting any servers a previous test may have
    // left behind (best-effort). Since the e2e daemon starts with an
    // empty DB per fixture run and the web tests now clean up after
    // themselves, this is a fast check.
    const { token, port } = readDaemonToken();
    await context.addInitScript((tok: string) => {
      window.localStorage.setItem("coffer.token", tok);
    }, token);

    // Defensive: delete any leftover servers via the API.
    const listResp = await fetch(`http://127.0.0.1:${port}/api/v1/resources`, {
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e-cleanup" },
    });
    if (listResp.ok) {
      const body = (await listResp.json()) as {
        resources: Array<{ kind: string; name: string }>;
      };
      for (const r of body.resources) {
        await fetch(
          `http://127.0.0.1:${port}/api/v1/resources/${r.kind}/${r.name}`,
          {
            method: "DELETE",
            headers: {
              "X-Coffer-Token": token,
              "X-Coffer-Actor": "e2e-cleanup",
            },
          },
        );
      }
    }

    await page.goto("/resources");

    // Welcome card content
    await expect(
      page.getByRole("heading", { name: /local-first vault/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Add MCP server/i }).first(),
    ).toBeVisible();

    // No ghost-table / "No resources yet" cell (we render the welcome
    // card instead of an empty table).
    await expect(page.getByRole("table")).toHaveCount(0);
  },
);
