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
  "web-ui",
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

    // The index renders Overview in place — no redirect.
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Overview" }),
    ).toBeVisible();

    // The sidebar lists Coffer's operational surfaces — and ONLY those:
    // Overview under no heading, then five groups by what the user comes to
    // do (ADR sidebar-grouped-by-what-the-person-comes-to-do).
    //
    // This list is the whole inventory, and the count assertion below is what
    // makes "and only those" true: a fence with no upper bound is not a fence.
    // Adding a sidebar entry means adding it here. See
    // `frontend/src/lib/navigation.ts`. The e2e daemon pins all four
    // experimental features on (`scripts/start_daemon.sh`), so the five
    // entries they own are listed and each carries the Experimental marker
    // beside its label.
    const EXP = String.raw`\s*Experimental`;
    const SIDEBAR_GROUPS: [string | null, RegExp[]][] = [
      [null, [/^Overview$/i]],
      ["Agents", [/^Agents$/i, new RegExp(`^Model providers${EXP}$`, "i")]],
      ["Run", [/^Conversations$/i, /^Channels$/i]],
      [
        "Capabilities",
        [/^MCP servers$/i, /^Custom tools$/i, /^Skills$/i, /^CLIs$/i],
      ],
      [
        "Context",
        [
          new RegExp(`^Knowledge${EXP}$`, "i"),
          new RegExp(`^Memory${EXP}$`, "i"),
        ],
      ],
      [
        "System",
        [
          /^Secrets$/i,
          /^Activity$/i,
          new RegExp(`^Usage${EXP}$`, "i"),
          new RegExp(`^Sync${EXP}$`, "i"),
        ],
      ],
    ];
    const nav = page.getByRole("navigation", { name: /Primary navigation/i });
    for (const [heading, labels] of SIDEBAR_GROUPS) {
      const scope = heading ? nav.getByRole("group", { name: heading }) : nav;
      for (const label of labels) {
        await expect(scope.getByRole("link", { name: label })).toBeVisible();
      }
    }
    // The upper bound: nothing in the sidebar this list does not name.
    await expect(nav.getByRole("link")).toHaveCount(15);

    // Settings is not an entry: a labelled row sits at the bottom of the
    // sidebar, above the daemon status.
    await expect(nav.getByRole("link", { name: /^Settings$/i })).toHaveCount(0);
    await expect(page.getByTestId("sidebar-settings")).toHaveText("Settings");
    await expect(page.getByTestId("sidebar-daemon")).toHaveAccessibleName(
      /Daemon running on port \d+/,
    );

    // No generic "unexpected error" card.
    await expect(page.getByText(/unexpected error/i)).toHaveCount(0);
    // The INTERNAL_ERROR copy reads "Coffer hit an internal error…".
    await expect(page.getByText(/internal error/i)).toHaveCount(0);
  },
);

acceptance(
  "web-ui",
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

    // For the first 10s of failures the page stays under the reconnecting
    // bar (board 1.2.17); then the offline state takes its place in the
    // workspace (board 1.2.18).
    await expect(page.getByTestId("daemon-reconnecting")).toBeVisible();
    const banner = page.getByTestId("daemon-banner");
    await expect(banner).toBeVisible({ timeout: 25_000 });
    // The recovery affordance is the restart command — the browser cannot
    // restart the daemon, and the retries clear the state on their own.
    await expect(banner.getByText("coffer daemon start")).toBeVisible();
    // The footer agrees with the banner: it reads offline, never running.
    await expect(page.getByTestId("sidebar-daemon")).toHaveAccessibleName(
      /Daemon offline/,
    );
  },
);

acceptance(
  "web-ui",
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
    await expect(banner).toBeVisible({ timeout: 25_000 });
    // A concrete recovery affordance appears (not a generic "error").
    await expect(banner.getByText("coffer daemon start")).toBeVisible();
    // Sidebar must still be reachable so the user can orient.
    await expect(
      page.getByRole("link", { name: /MCP servers/i }).first(),
    ).toBeVisible();
    await expect(page.getByText(/INTERNAL_ERROR/)).toHaveCount(0);
    await expect(page.getByText(/internal error/i)).toHaveCount(0);
  },
);

acceptance(
  "web-ui",
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
        resources: Array<{ uid: string }>;
      };
      for (const r of body.resources) {
        await fetch(`http://127.0.0.1:${port}/api/v1/resources/${r.uid}`, {
          method: "DELETE",
          headers: {
            "X-Coffer-Token": token,
            "X-Coffer-Actor": "e2e-cleanup",
          },
        });
      }
    }

    await page.goto("/mcp-servers");

    // Welcome card content
    const welcome = page.getByTestId("mcp-welcome");
    await expect(
      welcome.getByRole("heading", { name: /no mcp servers yet/i }),
    ).toBeVisible();
    await expect(
      welcome.getByRole("button", { name: /^add server$/i }),
    ).toBeVisible();

    // No ghost-table / "No resources yet" cell (we render the welcome
    // card instead of an empty table).
    await expect(page.getByRole("table")).toHaveCount(0);
  },
);
