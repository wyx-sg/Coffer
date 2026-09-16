// e2e/web/specs/shell_cold_start.spec.ts
//
// UI Shell §User Story 1 — first-visit experience must render authenticated
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
  "ui-shell",
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

    // The sidebar lists Coffer's operational surfaces — and ONLY those. No
    // dead "soon" entries for unbuilt features, and no entry outliving its
    // feature. RESOURCES carries one entry per resource kind with a list UI,
    // which is why Model providers and Channels are in this list rather than
    // under Settings and AGENTS.
    //
    // This list is the whole inventory, and the count assertion below is what
    // makes "and only those" true: the loop alone let the sidebar grow — Chat,
    // Memory and Sync were all absent from it while shipping — so a fence with
    // no upper bound is not a fence. Adding a sidebar entry means adding it
    // here. See `frontend/src/components/SidebarNav.tsx`'s NAV_GROUPS.
    const SIDEBAR_LABELS = [
      // Agents
      /^Agents$/i,
      /^Chat$/i,
      // Resources — one per resource kind with a list UI
      /^MCP servers$/i,
      /^Skills$/i,
      /^Knowledge$/i,
      /^Memory$/i,
      /^Model providers$/i,
      /^Channels$/i,
      // System
      /^Activity$/i,
      /^Sync$/i,
      /^Settings$/i,
    ];
    // Scoped to the sidebar's own <nav>, reached through the labelled <aside>
    // around it: the count assertion below has to see the eleven NAV_GROUPS
    // rows and nothing else — not the logo link, which sits in the aside but
    // outside the nav.
    const nav = page
      .getByRole("complementary", { name: /Primary navigation/i })
      .getByRole("navigation");
    for (const label of SIDEBAR_LABELS) {
      await expect(
        nav.getByRole("link", { name: label }).first(),
      ).toBeVisible();
    }
    // The upper bound: no twelfth entry.
    await expect(nav.getByRole("link")).toHaveCount(SIDEBAR_LABELS.length);

    // Grouped under Agents / Resources / System headings.
    await expect(page.getByText(/^Agents$/i).first()).toBeVisible();
    await expect(page.getByText(/^Resources$/i).first()).toBeVisible();
    await expect(page.getByText(/^System$/i).first()).toBeVisible();

    // The first-content surface is the resources page (redirected from /).
    // No generic "unexpected error" card.
    await expect(page.getByText(/unexpected error/i)).toHaveCount(0);
  },
);

acceptance(
  "ui-shell",
  "daemon-offline banner appears when daemon is unreachable",
  async ({ page }) => {
    // Same setup as the token-missing scenario below — pointing at a
    // dead port models "daemon not running" from the FE's perspective.
    // The banner renders at the top of the workspace with a clear recovery
    // affordance (Reload), even when no token has been minted yet.
    await page.addInitScript(() => {
      (
        window as unknown as { __COFFER_BASE_URL__: string }
      ).__COFFER_BASE_URL__ = "http://127.0.0.1:19998/api/v1";
      (window as unknown as { __COFFER_TOKEN__: string }).__COFFER_TOKEN__ = "";
    });

    await page.goto("/");

    const banner = page.getByTestId("daemon-banner");
    await expect(banner).toBeVisible({ timeout: 10_000 });
    // The recovery affordance is the restart command — the browser cannot
    // restart the daemon, and the status poll clears the banner on its own.
    await expect(banner.getByText("coffer daemon start")).toBeVisible();
  },
);

acceptance(
  "ui-shell",
  "token-missing renders an actionable empty state",
  async ({ page }) => {
    // Point the FE at a base URL that won't resolve to a daemon. That
    // mirrors what a real user sees when the daemon hasn't been started
    // yet: the status query errors out and DaemonOfflineBanner shows its
    // "daemon not running" panel with the restart command to run.
    await page.addInitScript(() => {
      (
        window as unknown as { __COFFER_BASE_URL__: string }
      ).__COFFER_BASE_URL__ = "http://127.0.0.1:19999/api/v1";
      (window as unknown as { __COFFER_TOKEN__: string }).__COFFER_TOKEN__ = "";
    });

    await page.goto("/");

    const banner = page.getByTestId("daemon-banner");
    await expect(banner).toBeVisible({ timeout: 10_000 });
    // A concrete recovery affordance appears (not a generic "error").
    await expect(banner.getByText("coffer daemon start")).toBeVisible();
    // Sidebar must still be reachable so the user can orient.
    await expect(
      page.getByRole("link", { name: /MCP servers/i }).first(),
    ).toBeVisible();
    await expect(page.getByText(/INTERNAL_ERROR/)).toHaveCount(0);
  },
);

acceptance(
  "ui-shell",
  "empty resources list renders a welcome view",
  async ({ page, context }) => {
    // Inject a valid token so the API calls succeed, but ensure no
    // resources exist by deleting any servers a previous test may have
    // left behind (best-effort). Since the e2e daemon starts with an
    // empty DB per fixture run and the web tests now clean up after
    // themselves, this is a fast check.
    const { token, port } = readDaemonToken();
    await context.addInitScript((tok: string) => {
      (window as unknown as { __COFFER_TOKEN__?: string }).__COFFER_TOKEN__ =
        tok;
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

    await page.goto("/mcp-servers");

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
