import { defineConfig, devices } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ESM-compatible equivalents of __dirname / __filename
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ROOT = path.resolve(__dirname, "..");

// COFFER_E2E_WEB_PORT and COFFER_E2E_PORT move the suite off :5173 / :18000
// when another checkout's dev server holds them. Off the default web port the
// daemon's dev CORS list (:5173 only) no longer matches, so the Vite origin is
// passed explicitly, and the HOME pointer moves so the two suites don't share it.
const WEB_PORT = Number(process.env.COFFER_E2E_WEB_PORT ?? 5173);
const DAEMON_PORT = Number(process.env.COFFER_E2E_PORT ?? 18000);
const WEB_ORIGIN = `http://localhost:${WEB_PORT}`;
const MOVED = WEB_PORT !== 5173 || DAEMON_PORT !== 18000;
if (MOVED && !process.env.COFFER_E2E_HOME_FILE) {
  process.env.COFFER_E2E_HOME_FILE = `/tmp/coffer-e2e-home-${DAEMON_PORT}.path`;
}

export default defineConfig({
  fullyParallel: false, // sequential — all tests share the same daemon instance
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0, // a flaky spec must fail, not pass on a second attempt (.agents/testing.md)
  reporter: [["list"]],

  webServer: [
    {
      // Daemon: isolated HOME via start_daemon.sh, on port 18000 unless moved.
      // reuseExistingServer=true in local dev so repeated `npm test` runs
      // reuse the already-running daemon rather than fighting TCP TIME_WAIT.
      // In CI (reuseExistingServer=false) a fresh daemon is always spawned.
      // timeout=90s to accommodate the 45s port-wait in start_daemon.sh plus
      // ~5s for Alembic migrations and uvicorn startup.
      command: "bash ./scripts/start_daemon.sh",
      url: `http://127.0.0.1:${DAEMON_PORT}/api/v1/daemon/status`,
      timeout: 90_000,
      reuseExistingServer: !process.env.CI,
      cwd: __dirname,
      env: {
        COFFER_E2E_PORT: String(DAEMON_PORT),
        ...(MOVED
          ? {
              COFFER_E2E_HOME_FILE: process.env.COFFER_E2E_HOME_FILE ?? "",
              COFFER_CORS_ORIGINS: `${WEB_ORIGIN},http://127.0.0.1:${WEB_PORT}`,
            }
          : {}),
      },
    },
    {
      // Vite dev server pointed at the e2e daemon.
      // IMPORTANT: reuseExistingServer is intentionally false (even in local
      // dev) for the Vite entry.  A reused `make dev` Vite instance lacks
      // VITE_COFFER_BASE_URL, so the app silently falls back to port 38470
      // (no daemon there) and all API calls fail with "Failed to fetch".
      // The daemon entry above still reuses to avoid TCP TIME_WAIT delays;
      // Vite starts quickly enough that a fresh start per run is fine.
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      url: WEB_ORIGIN,
      timeout: 60_000,
      reuseExistingServer: false,
      cwd: path.join(ROOT, "frontend"),
      env: {
        VITE_COFFER_BASE_URL: `http://127.0.0.1:${DAEMON_PORT}/api/v1`,
        // The Query devtools' floating button sits over the bottom-left corner
        // and intercepts clicks on controls there.
        VITE_COFFER_NO_DEVTOOLS: "1",
      },
    },
  ],

  projects: [
    // -----------------------------------------------------------------------
    // web — browser-driven acceptance tests for the Coffer frontend UI
    // -----------------------------------------------------------------------
    {
      name: "web",
      testDir: "./web/specs",
      use: {
        baseURL: WEB_ORIGIN,
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
        ...devices["Desktop Chrome"],
      },
    },
    // -----------------------------------------------------------------------
    // mcp — cross-process acceptance tests for the MCP gateway
    // No browser needed: tests spawn OS subprocesses (daemon + shim) directly.
    // -----------------------------------------------------------------------
    {
      name: "mcp",
      testDir: "./mcp/specs",
      // No browser; `page` fixture is unavailable in these tests.
    },
  ],
});
