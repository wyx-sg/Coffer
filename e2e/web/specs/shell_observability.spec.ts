// e2e/web/specs/shell_observability.spec.ts
//
// Spec 002 §User Story 3 — Observability is currently the audit log: a
// filterable table of every resource/capability lifecycle event. The
// legacy /audit URL redirects in.

import { expect } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { acceptance } from "./_acceptance";
import {
  beforeEachInjectToken,
  deregisterMcpServer,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.join(REPO_ROOT, ".venv/bin/python3");
const FAKE_SERVER = path.join(
  REPO_ROOT,
  "backend/tests/fixtures/fake_mcp_server.py",
);

beforeEachInjectToken();

// Registering a server writes audit rows — enough to populate the table.
// `extraArgs` are appended verbatim after the scenario flag, matching the
// shape used in shell_mcp_flows.spec.ts so both helpers are identical.
async function registerFakeServer(
  name: string,
  extraArgs: string[] = ["--tools", "read_file"],
): Promise<void> {
  const { token, port } = readDaemonToken();
  const r = await fetch(`http://127.0.0.1:${port}/api/v1/resources`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    body: JSON.stringify({
      kind: "mcp_server",
      name,
      config: {
        transport: {
          type: "stdio",
          command: PYTHON,
          args: [FAKE_SERVER, "--scenario", "basic", ...extraArgs],
        },
      },
    }),
  });
  if (!r.ok) throw new Error(`register failed: ${r.status} ${await r.text()}`);
}

/**
 * Trigger capability refresh so that capability_first_seen audit events
 * are created synchronously before the test reads the audit log.
 */
async function refreshServer(name: string): Promise<void> {
  const { token, port } = readDaemonToken();
  const r = await fetch(
    `http://127.0.0.1:${port}/api/v1/resources/mcp_server/${name}/refresh`,
    {
      method: "POST",
      headers: { "X-Coffer-Token": token, "X-Coffer-Actor": "e2e" },
    },
  );
  if (!r.ok) throw new Error(`refresh failed: ${r.status} ${await r.text()}`);
}

acceptance(
  "002-ui-shell",
  "observability route renders the audit log",
  async ({ page }) => {
    const name = generateUniqueName("e2e002obs");
    try {
      await registerFakeServer(name);
      await page.goto("/observability");
      await expect(
        page.getByRole("heading", { name: /^Audit log$/ }),
      ).toBeVisible();
      // The time + actor filter bar renders, and the table picks up the
      // new row as a plain-language activity line mentioning the server.
      await expect(page.getByText("Time range")).toBeVisible();
      await expect(page.getByText(new RegExp(name))).toBeVisible({
        timeout: 10_000,
      });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "legacy /audit redirects to Observability",
  async ({ page }) => {
    await page.goto("/audit");
    await expect(page).toHaveURL(/\/observability$/);
    await expect(
      page.getByRole("heading", { name: /^Audit log$/ }),
    ).toBeVisible();
  },
);

acceptance(
  "002-ui-shell",
  "audit log row expand shows detail panel",
  async ({ page }) => {
    const name = generateUniqueName("e2e002rowex");
    try {
      await registerFakeServer(name);
      await page.goto("/observability");
      // Wait for the row mentioning the server to appear
      const row = page.getByRole("row").filter({ hasText: name }).first();
      await expect(row).toBeVisible({ timeout: 10_000 });

      // Before clicking: the detail panel must not exist in the DOM at all
      // (not.toBeVisible() is vacuous when the element is absent; toHaveCount(0)
      // genuinely fails if the panel is already open).
      await expect(page.getByText("Server registered")).toHaveCount(0);

      // Click the row to expand it
      await row.click();

      // After clicking: the detail panel renders the event label
      await expect(page.getByText("Server registered")).toBeVisible({
        timeout: 5_000,
      });
    } finally {
      await deregisterMcpServer(name);
    }
  },
);

acceptance(
  "002-ui-shell",
  "audit log free-text filter narrows rows",
  async ({ page }) => {
    // Register two servers with distinct names so we can filter one out.
    const nameA = generateUniqueName("e2e002filtA");
    const nameB = generateUniqueName("e2e002filtB");
    try {
      await registerFakeServer(nameA);
      await registerFakeServer(nameB);
      await page.goto("/observability");

      // Both servers appear initially
      await expect(page.getByText(new RegExp(nameA))).toBeVisible({
        timeout: 10_000,
      });
      await expect(page.getByText(new RegExp(nameB))).toBeVisible({
        timeout: 10_000,
      });

      // Type the first server name into the search box
      const searchInput = page.getByPlaceholder("Search activity");
      await searchInput.fill(nameA);

      // The first server's row remains visible; the second is gone
      await expect(page.getByText(new RegExp(nameA))).toBeVisible({
        timeout: 5_000,
      });
      await expect(page.getByText(new RegExp(nameB))).toHaveCount(0);
    } finally {
      await deregisterMcpServer(nameA);
      await deregisterMcpServer(nameB);
    }
  },
);

acceptance(
  "002-ui-shell",
  "audit log pagination controls appear and advance page",
  async ({ page }) => {
    // Register a server with 20 tools so that capability_first_seen events
    // plus resource_created totals 21 entries — just over the default page
    // size of 20, forcing a second page.
    //
    // Because the audit log is shared across all tests in the run, we must
    // assert the DELTA caused by THIS test rather than assuming the page
    // starts empty.  Strategy: load /observability BEFORE registering the new
    // server, record whether Next is currently enabled, then register+refresh,
    // reload, and assert that Next became (or stayed) enabled AND that a new
    // page boundary appeared that is attributable to this server's events.
    const name = generateUniqueName("e2e002pag");
    const MANY_TOOLS = [
      "t01",
      "t02",
      "t03",
      "t04",
      "t05",
      "t06",
      "t07",
      "t08",
      "t09",
      "t10",
      "t11",
      "t12",
      "t13",
      "t14",
      "t15",
      "t16",
      "t17",
      "t18",
      "t19",
      "t20",
    ];
    try {
      // ── Step 1: capture baseline page count BEFORE this test's writes ──
      await page.goto("/observability");
      // Wait for the audit table to be ready (heading is always present)
      await expect(
        page.getByRole("heading", { name: /^Audit log$/ }),
      ).toBeVisible({ timeout: 10_000 });

      // Read the current "Page X of Y" text if it exists (may not if < 21
      // total entries so far).  We capture it to compare after.
      const pageInfoBefore = await page
        .getByText(/Page \d+ of \d+/)
        .first()
        .textContent()
        .catch(() => null);
      // Parse the total-page count from "Page 1 of N" (null ⇒ 0 pages so far)
      const pagesBefore = pageInfoBefore
        ? parseInt(/Page \d+ of (\d+)/.exec(pageInfoBefore)?.[1] ?? "1", 10)
        : 1;

      // ── Step 2: register the 20-tool server and trigger discovery ──
      await registerFakeServer(name, ["--tools", ...MANY_TOOLS]);
      // Trigger discovery synchronously so all capability_first_seen events
      // exist before the page reloads.
      await refreshServer(name);

      // ── Step 3: reload and wait for this server's entries to appear ──
      await page.reload();
      await expect(page.getByText(new RegExp(name)).first()).toBeVisible({
        timeout: 15_000,
      });

      // ── Step 4: assert pagination GREW because of this test's 21 events ──
      // The page count reported by "Page X of Y" must be strictly greater
      // than what it was before we registered this server — proving that
      // pagination is driven by THIS test's writes, not pre-existing rows.
      const nextBtn = page.getByRole("button", { name: "Next" });
      await expect(nextBtn).toBeEnabled({ timeout: 5_000 });

      const pageInfoAfter = await page
        .getByText(/Page \d+ of \d+/)
        .first()
        .textContent({ timeout: 5_000 });
      const pagesAfter = parseInt(
        /Page \d+ of (\d+)/.exec(pageInfoAfter ?? "")?.[1] ?? "0",
        10,
      );
      expect(pagesAfter).toBeGreaterThan(pagesBefore);

      // Click Next — we should move to page 2 (at minimum).
      // Use dispatchEvent to avoid the ReactQuery DevTools overlay that
      // intercepts pointer events at the bottom of the screen.
      // TODO: enable DevTools-off in e2e via env var (VITE_COFFER_BASE_URL
      // gates dev token injection — add a parallel gate for ReactQueryDevtools
      // so this workaround can be replaced with a normal `.click()`).
      await nextBtn.dispatchEvent("click");
      await expect(page.getByText(/Page 2 of/)).toBeVisible({ timeout: 5_000 });

      // Bind the assertion to data this test created, not the page count
      // alone: at least one row mentioning the just-registered server must
      // appear on page 2. Without this we'd pass even if pagination
      // silently rendered an empty second page.
      await expect(
        page
          .getByRole("row")
          .filter({ hasText: new RegExp(name) })
          .first(),
      ).toBeVisible({ timeout: 10_000 });

      // The "Previous" button should now be enabled on page 2.
      const prevBtn = page.getByRole("button", { name: "Previous" });
      await expect(prevBtn).toBeEnabled();
    } finally {
      await deregisterMcpServer(name);
    }
  },
);
