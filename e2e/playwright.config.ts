import { defineConfig } from "@playwright/test";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ESM-compatible equivalents of __dirname / __filename
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  fullyParallel: false, // sequential — all tests share the same daemon instance
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],

  webServer: [
    {
      // Daemon: isolated HOME via start_daemon.sh, always on port 18000.
      // reuseExistingServer=true in local dev so repeated `npm test` runs
      // reuse the already-running daemon rather than fighting TCP TIME_WAIT.
      // In CI (reuseExistingServer=false) a fresh daemon is always spawned.
      // timeout=90s to accommodate the 45s port-wait in start_daemon.sh plus
      // ~5s for Alembic migrations and uvicorn startup.
      command: "bash ./scripts/start_daemon.sh",
      url: "http://127.0.0.1:18000/api/v1/daemon/status",
      timeout: 90_000,
      reuseExistingServer: !process.env.CI,
      cwd: __dirname,
    },
  ],

  projects: [
    // -----------------------------------------------------------------------
    // mcp — cross-process acceptance tests for the MCP gateway
    // No browser needed: tests spawn OS subprocesses (daemon + shim) directly.
    // -----------------------------------------------------------------------
    {
      name: "mcp",
      testDir: "./mcp/specs",
      // No browser; `page` fixture is unavailable in these tests.
    },
    // NOTE: the browser-driven `web` project + its Vite webServer were removed
    // (CODE-044). The frontend UI is a separate follow-up spec; the old
    // `web` project pointed at a testDir that no longer exists and silently
    // collected zero tests, giving false green. Re-add both together with the
    // web-UI spec.
  ],
});
